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


def _artwork(name: str, variant: int):
    """A 1280x720 thumbnail from a bundled generated image, in two looks."""
    from PIL import Image, ImageEnhance, ImageOps

    folder = ROOT / "assets"
    path = folder / "preview_thumbnails" / (name + ".jpg")
    if not path.exists():
        path = folder / (name + ".png")
    image = Image.open(path).convert("RGB")
    width, height = image.size
    if variant:
        # Mirrored, a tighter crop from the other side, and a cooler, deeper grade.
        image = ImageOps.mirror(image)
        box = (int(width * 0.18), int(height * 0.12), width, height)
        image = image.crop(box)
        image = ImageEnhance.Color(image).enhance(1.15)
        image = ImageEnhance.Brightness(image).enhance(0.88)
        blue = Image.new("RGB", image.size, (40, 60, 120))
        image = Image.blend(image, blue, 0.12)
    return ImageOps.fit(image, (1280, 720), Image.Resampling.LANCZOS)


_TAGS = {
    "Mountain Mornings": ["mountains", "lake", "sunrise"],
    "Golden Hours": ["desert", "sunset", "golden hour"],
    "River Journal": ["river", "forest", "fog"],
    "Into the Canopy": ["rainforest", "waterfall"],
    "Quiet Peaks": ["mountains", "reflection", "blue hour"],
}


def _video_id(index: int) -> str:
    """A stable, YouTube-shaped 11-character ID for a fictional item."""
    import base64
    import hashlib

    digest = hashlib.sha256(f"vodforge-sample-{index}".encode()).digest()
    return base64.urlsafe_b64encode(digest).decode()[:11]


def _encode(ffmpeg: str, thumbnail: Path, media: Path, seconds: int, kind: str) -> None:
    common = [ffmpeg, "-hide_banner", "-loglevel", "error"]
    if kind == "MP4":
        command = common + [
            "-loop",
            "1",
            "-framerate",
            "30",
            "-i",
            str(thumbnail),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-t",
            str(seconds),
            "-vf",
            "scale=1280:720",
            "-r",
            "30",
            "-tune",
            "stillimage",
            "-c:v",
            "libx264",
            "-profile:v",
            "high",
            "-preset",
            "veryfast",
            "-crf",
            "21",
            "-g",
            "150",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-shortest",
            str(media),
        ]
    else:
        # Soft pink noise, filtered to sound like rain or water.
        command = common + [
            "-f",
            "lavfi",
            "-i",
            f"anoisesrc=color=pink:amplitude=0.25:duration={seconds}:sample_rate=48000",
            "-af",
            "lowpass=f=3200,highpass=f=120,volume=0.6,aformat=channel_layouts=stereo",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "320k",
            str(media),
        ]
    subprocess.run(command, check=True)


def _summary(media: Path, kind: str) -> dict:
    """Source facts for the fictional upload; output facts measured from the file."""
    probe = json.loads(
        subprocess.run(
            [
                shutil.which("ffprobe") or "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(media),
            ],
            capture_output=True,
            check=True,
            text=True,
        ).stdout
    )
    streams = {s["codec_type"]: s for s in probe["streams"]}
    a, f = streams["audio"], probe["format"]
    size = int(f["size"])
    duration = float(f["duration"])
    akbps = round(int(a.get("bit_rate") or f.get("bit_rate") or 0) / 1000)
    common_output = {
        "Audio sample rate": f"{a.get('sample_rate')} Hz",
        "Audio channels": str(a.get("channels")),
        "Measured audio bitrate": f"{akbps:,} kbps",
        "Output duration": f"{int(duration // 60)}:{int(duration % 60):02d}",
        "Output file size": f"{size / 1024 / 1024:.1f} MB",
        "Output file path": str(media),
        "Validation status": "Validated",
        "Output status": "Complete",
    }
    if kind == "MP3":
        return {
            "source": {
                "Source format selector used": "251",
                "Audio format ID": "251",
                "Source container/ext": "webm",
                "Source audio codec": "opus",
                "Source audio bitrate": "138 kbps",
                "Source audio sample rate": "48000",
                "Source audio channels": "2",
                "Effective MP3-equivalent audio bitrate": "138 kbps",
                "Reason selected": "highest-quality available audio-only source",
            },
            "output": {
                "Output container": "MP3",
                "Output audio codec": "MP3",
                "Target audio bitrate": "320 kbps",
                **common_output,
            },
            "warnings": [],
        }
    v = streams["video"]
    vkbps = round(int(v.get("bit_rate") or 0) / 1000)
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    seconds = round(duration)
    return {
        "source": {
            "Source format selector used": "136+140",
            "Video format ID": "136",
            "Audio format ID": "140",
            "Source container/ext": "mp4",
            "Source resolution": "1280x720",
            "Source frame rate": "30 fps",
            "Source video codec": "avc1.4d401f",
            "Source video bitrate": "1,480 kbps",
            "Source audio codec": "mp4a.40.2",
            "Source audio bitrate": "129 kbps",
            "Source audio sample rate": "44100",
            "Source audio channels": "2",
            "HDR/SDR status": "SDR",
            "File size estimate": f"{(1480 + 129) * seconds / 8 / 1024:.1f} MB",
            "Effective H.264-equivalent video bitrate": "1,480 kbps",
            "Effective AAC-equivalent audio bitrate": "129 kbps",
            "Reason selected": "highest-quality SDR source within the 720p ceiling",
        },
        "output": {
            "Output container": "MP4",
            "Output video codec": "H.264",
            "H.264 profile": v.get("profile", "High"),
            "Pixel format": v.get("pix_fmt", "yuv420p"),
            "Output resolution": f"{v['width']}x{v['height']}",
            "Output frame rate": f"{num / den:g} fps",
            "Output audio codec": "AAC",
            "Output rate-control mode": "CRF 21 (Everyday)",
            "Target video bitrate": "Quality-based",
            "Target audio bitrate": "160 kbps",
            "Measured video bitrate": f"{vkbps:,} kbps",
            **common_output,
        },
        "warnings": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument(
        "--media",
        type=Path,
        help="Where the sample media goes (default: HOME/Downloads). Use a "
        "separate volume so the Library storage card doesn't show your disk.",
    )
    args = parser.parse_args()
    home = args.home.expanduser().resolve()
    if home == Path.home().resolve() or home.exists():
        parser.error("Choose a new isolated HOME, never your current profile.")
    home.mkdir(parents=True)
    os.environ["HOME"] = str(home)
    os.environ["LOCALAPPDATA"] = str(home)
    os.environ["VODFORGE_DISABLE_TELEMETRY"] = "1"
    sys.path.insert(0, str(ROOT))
    from yt_downloader.download_service import save_cached_thumbnail_bytes
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
    # Fictional library: five channels, each with one playlist of two videos,
    # plus two MP3s. Artwork is made from the repository's generated nature
    # images; each base gives two looks (a crop, and a mirrored, regraded crop).
    catalog = [
        # title, base image, variant, playlist, channel, seconds, kind, description
        (
            "Still Water at First Light",
            "alpine-lake",
            0,
            "Mountain Mornings",
            "Northlight Journal",
            267,
            "MP4",
            "Mist lifts off the lake while the first light reaches the far ridge. We set up before dawn on the north shore and let the camera run as the reflection sharpened and the wind stayed still.",
        ),
        (
            "Above the Glacier Lake",
            "alpine-lake",
            1,
            "Mountain Mornings",
            "Northlight Journal",
            312,
            "MP4",
            "A slow climb to the lookout above the glacier lake, with the meltwater a deeper blue every switchback. Filmed over two mornings in early autumn.",
        ),
        (
            "Last Light on the Dunes",
            "desert-sunset",
            0,
            "Golden Hours",
            "Ochre Studio",
            228,
            "MP4",
            "The sun drops behind the ridge and the sky burns orange, then violet. A single take from the dune crest, from the last direct light to the first stars.",
        ),
        (
            "Canyon Afterglow",
            "desert-sunset",
            1,
            "Golden Hours",
            "Ochre Studio",
            195,
            "MP4",
            "Afterglow over the canyon rim as the wind settles and the rock cools. The light changes every minute; we left it uncut.",
        ),
        (
            "Where the River Bends",
            "forest-river",
            0,
            "River Journal",
            "Riverline Notes",
            284,
            "MP4",
            "Morning fog follows the river through the pines and burns off as the sun clears the valley wall. Recorded from the ridge trail above the second bend.",
        ),
        (
            "Fog Over the Valley",
            "forest-river",
            1,
            "River Journal",
            "Riverline Notes",
            241,
            "MP4",
            "The valley fills with fog after a night of rain, then slowly clears to reveal the river and the forest on both banks.",
        ),
        (
            "Under the Canopy",
            "rainforest-falls",
            0,
            "Into the Canopy",
            "Fernwood Films",
            356,
            "MP4",
            "A hidden waterfall under the rainforest canopy, reached after an hour on a narrow path. The pool below stays clear even after heavy rain, and the falls are loudest just after sunrise.",
        ),
        (
            "The Emerald Pool",
            "rainforest-falls",
            1,
            "Into the Canopy",
            "Fernwood Films",
            203,
            "MP4",
            "Clear water and green light at the foot of the falls. A quiet hour at the pool, filmed from the rocks on the far side.",
        ),
        (
            "When the Ridge Turns Pink",
            "watch-welcome-scenic",
            0,
            "Quiet Peaks",
            "Summit Weekly",
            252,
            "MP4",
            "For a few minutes the ridgeline glows pink above the still water, then fades to blue. Filmed from the eastern shore on a windless evening.",
        ),
        (
            "Night Falls on the Peaks",
            "watch-welcome-scenic",
            1,
            "Quiet Peaks",
            "Summit Weekly",
            289,
            "MP4",
            "Blue hour settles over the peaks and their reflection as the last light leaves the summits.",
        ),
        (
            "Rain on the Canopy",
            "rainforest-falls",
            1,
            "Into the Canopy",
            "Fernwood Films",
            184,
            "MP3",
            "Steady rain on the leaves, recorded under the canopy beside the falls. Two microphones, no music.",
        ),
        (
            "River Sounds at Dawn",
            "forest-river",
            0,
            "River Journal",
            "Riverline Notes",
            216,
            "MP3",
            "The river and the first birds before sunrise, recorded at the second bend.",
        ),
    ]
    records = []
    media_root = args.media.expanduser().absolute() if args.media else home / "Downloads"
    for index, (
        title,
        image,
        variant,
        playlist,
        channel,
        seconds,
        kind,
        description,
    ) in enumerate(catalog):
        video_id = _video_id(index)
        output = media_root / channel / "playlists" / playlist / f"{title} [{video_id}]"
        output.mkdir(parents=True)
        thumbnail = output / "thumbnail.jpg"
        _artwork(image, variant).save(thumbnail, quality=92)
        media = output / (title + (".mp4" if kind == "MP4" else ".mp3"))
        _encode(ffmpeg, thumbnail, media, seconds, kind)
        job = DownloadJob(
            url=f"https://www.youtube.com/watch?v={video_id}",
            output_dir=media_root,
            output_type=OutputType.MP4 if kind == "MP4" else OutputType.MP3,
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
            tags=[],
        )
        info = annotate_job_metadata(
            job,
            {
                "id": video_id,
                "title": title,
                "channel": channel,
                "uploader": channel,
                "duration": seconds,
                "playlist_id": "PL" + _video_id(100 + len(playlist)) + playlist[:4],
                "playlist_title": playlist,
                "webpage_url": job.url,
                "description": description,
                "tags": _TAGS[playlist],
                "vodforge_output_type": kind,
                "vodforge_output_path": str(media),
                "vodforge_encoding_summary": _summary(media, kind),
                "vodforge_run_activity": [
                    (
                        "INFO: selected format 136+140 — video 720p h264; audio AAC"
                        if kind == "MP4"
                        else "INFO: selected format 251 — audio opus"
                    ),
                    "INFO: downloading media",
                    "INFO: ffmpeg command started",
                    "INFO: validated output",
                    "INFO: packaged media file",
                    "INFO: Download complete",
                ],
            },
        )
        info["vodforge_output_dir"] = str(output)
        info["vodforge_run_id"] = job.run_id
        info["vodforge_retry_job"] = serialize_download_job(job)
        info["vodforge_saved_at"] = f"2026-11-{12 + index:02d}T10:00:00+00:00"
        (output / "metadata.json").write_text(
            json.dumps(info, indent=2), encoding="utf-8"
        )
        save_cached_thumbnail_bytes(info, thumbnail.read_bytes())
        records.append(info)
    save_history(history_file_path(), records)
    stopped = DownloadJob(
        url=f"https://www.youtube.com/watch?v={_video_id(99)}",
        output_dir=media_root,
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
        "id": _video_id(99),
        "title": "Coastal Trail at Low Tide",
        "channel": "Riverline Notes",
        "duration": 247,
    }
    stopped.activity_lines = [
        "INFO: selected format 137+140 — video 1080p h264; audio AAC",
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
    from yt_downloader.settings_store import save_settings, settings_file_path

    save_settings(
        settings_file_path(),
        {
            "output_dir": str(media_root),
            "theme_name": "Matte",
            "theme_accent": "Violet",
            "social_invitation_dismissed": True,
        },
    )
    (home / "fixture-provenance.json").write_text(
        json.dumps(
            {
                "fictional": True,
                "telemetry": "disabled",
                "source": str(ROOT),
                "images": sorted({row[1] for row in catalog}),
                "media": "local still-image MP4s with silent audio; MP3s of generated noise",
                "network_downloads": False,
            },
            indent=2,
        )
    )
    print(home)


if __name__ == "__main__":
    main()
