"""Seed an explicitly isolated native screenshot profile with fictional nature media.

This writes fixture data only. Screenshots must be captured from the real app;
it never draws or alters UI pixels, submits downloads, or uses a real library.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True)
    args = parser.parse_args()
    home = args.home.expanduser().resolve()
    if home == Path.home().resolve() or home.exists():
        parser.error("Choose a new isolated HOME, never your current profile.")
    home.mkdir(parents=True)
    os.environ["HOME"] = str(home)
    os.environ["LOCALAPPDATA"] = str(home)
    os.environ["VODFORGE_DISABLE_TELEMETRY"] = "1"
    sys.path.insert(0, str(ROOT))
    from yt_downloader.app import save_cached_thumbnail_bytes
    from yt_downloader.engagement_state import EngagementState
    from yt_downloader.history import (
        application_data_dir,
        history_file_path,
        save_history,
    )
    from yt_downloader.models import (
        DownloadJob,
        ExportMode,
        ManualExportSettings,
        Mp3ExportSettings,
        OutputType,
    )
    from yt_downloader.run_identity import annotate_job_metadata
    from yt_downloader.run_state import (
        RunRecoveryOwner,
        run_state_file_path,
        serialize_download_job,
    )

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("FFmpeg is needed for real sample playback.")
    catalog = [
        ("Alpine lake at dawn", "alpine-lake", "Quiet mountains", "Northlight Nature"),
        ("Desert sunset", "desert-sunset", "Open horizons", "Northlight Nature"),
        ("Forest river", "forest-river", "Forest & water", "Wild Places"),
        ("Rainforest falls", "rainforest-falls", "Forest & water", "Wild Places"),
    ]
    records = []
    for index, (title, image, playlist, channel) in enumerate(catalog):
        output = home / "Downloads" / "Nature Library" / playlist / title
        output.mkdir(parents=True)
        thumbnail = output / "thumbnail.jpg"
        shutil.copy2(
            ROOT / "assets" / "preview_thumbnails" / (image + ".jpg"), thumbnail
        )
        video = output / (title + ".mp4")
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-loop",
                "1",
                "-i",
                str(thumbnail),
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=48000:cl=stereo",
                "-t",
                "30",
                "-vf",
                "scale=1280:720",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "22",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(video),
            ],
            check=True,
        )
        job = DownloadJob(
            url=f"https://example.invalid/nature/{image}",
            output_dir=home / "Downloads",
            output_type=OutputType.MP4,
            quality_label="720p HD",
            export_mode=ExportMode.EVERYDAY,
            manual_settings=ManualExportSettings(),
            mp3_settings=Mp3ExportSettings(),
            single_video_only=True,
            use_nvenc=False,
            embed_thumbnail=False,
            write_thumbnail=True,
            embed_metadata=True,
            write_info_json=True,
            tags=["nature", "sample"],
        )
        info = annotate_job_metadata(
            job,
            {
                "id": f"nature-demo-{index}",
                "title": title,
                "channel": channel,
                "uploader": channel,
                "duration": 30,
                "playlist_id": playlist.lower().replace(" ", "-"),
                "playlist_title": playlist,
                "webpage_url": job.url,
                "description": f"A quiet moment in nature: {title.lower()}. Fictional sample media for the VODForge design preview.",
                "tags": ["nature", "sample"],
                "vodforge_output_type": "MP4",
                "vodforge_output_path": str(video),
                "vodforge_encoding_summary": {
                    "source": {
                        "Source resolution": "1280x720",
                        "Video codec": "H.264",
                        "Audio codec": "AAC",
                    },
                    "output": {
                        "Output resolution": "1280x720",
                        "Output container": "MP4",
                        "Output file size": f"{video.stat().st_size / 1024 / 1024:.1f} MB",
                        "Output file path": str(video),
                    },
                },
                "vodforge_run_activity": [
                    "INFO: selected format demo — video 720p h264; audio AAC",
                    "INFO: downloading media",
                    "INFO: ffmpeg command started",
                    "INFO: validated output",
                    "INFO: packaged media file",
                    "INFO: Download complete",
                ],
            },
        )
        info["vodforge_output_dir"] = str(output)
        info["vodforge_retry_job"] = serialize_download_job(job)
        info["vodforge_saved_at"] = f"2026-09-29T10:0{index}:00+00:00"
        (output / "metadata.json").write_text(
            json.dumps(info, indent=2), encoding="utf-8"
        )
        save_cached_thumbnail_bytes(info, thumbnail.read_bytes())
        records.append(info)
    save_history(history_file_path(), records)
    stopped = DownloadJob(
        url="https://example.invalid/nature/coastal-trail",
        output_dir=home / "Downloads",
        output_type=OutputType.MP4,
        quality_label="1080p Full HD",
        export_mode=ExportMode.EVERYDAY,
        manual_settings=ManualExportSettings(),
        mp3_settings=Mp3ExportSettings(),
        single_video_only=True,
        use_nvenc=False,
        embed_thumbnail=False,
        write_thumbnail=True,
        embed_metadata=True,
        write_info_json=True,
        tags=[],
    )
    stopped.preview_info = {
        "id": "nature-demo-stopped",
        "title": "Coastal trail",
        "channel": "Wild Places",
        "duration": 30,
    }
    stopped.activity_lines = [
        "INFO: selected format demo — video 1080p h264",
        "INFO: downloading media",
        "INFO: Download stopped",
    ]
    save_cached_thumbnail_bytes(
        stopped.preview_info,
        (ROOT / "assets/preview_thumbnails/forest-river.jpg").read_bytes(),
    )
    RunRecoveryOwner(run_state_file_path()).terminal_attempt(
        stopped, "Stopped", "Download stopped"
    )
    data = application_data_dir()
    EngagementState(data / "installation.json").presented_welcome()
    (data / "settings.json").write_text(
        json.dumps(
            {
                "output_dir": str(home / "Downloads"),
                "theme_name": "Matte",
                "theme_accent": "Violet",
            }
        ),
        encoding="utf-8",
    )
    (home / "fixture-provenance.json").write_text(
        json.dumps(
            {
                "fictional": True,
                "telemetry": "disabled",
                "source": str(ROOT),
                "images": [row[1] for row in catalog],
                "media": "30-second local still-image MP4s with silent audio",
                "network_downloads": False,
            },
            indent=2,
        )
    )
    print(home)


if __name__ == "__main__":
    main()
