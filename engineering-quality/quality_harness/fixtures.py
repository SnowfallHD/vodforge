from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .util import sha256_file

UNICODE_TITLE = (
    "A/B test — Δοκιμή_日本語_emoji-🚀_quotes-'double'_colon:_question?_asterisk*_|pipe|_"
    "a deliberately long title that pressures path budgets without being meaningless"
)

LIBRARY_DESCRIPTION_STRESS_TITLE = (
    "Library visibility regression — Δοκιμή_日本語_🚀 — "
    "an intentionally extreme selected-item title whose wrapped height must never "
    "displace the Description heading or body; the output path is deliberately long "
    "and must be ellipsized before this title is shortened — "
    "final sentinel segment for deterministic packaged UI evidence"
)
# The page exposes the same media through both ``og:video`` and ``video[src]``.
# The pinned yt-dlp Generic extractor numbers those discovered entries, and the
# packaged single-video journey selects the first one. Keep this expected
# provider result explicit so UI identity evidence remains exact rather than
# accepting a permissive title suffix.
LIBRARY_DESCRIPTION_STRESS_SELECTED_TITLE = f"{LIBRARY_DESCRIPTION_STRESS_TITLE} (1)"
LIBRARY_DESCRIPTION_STRESS_DESCRIPTION = (
    "Description visibility sentinel: this nonempty text must remain visible in the "
    "fixed-height Selected Item panel."
)


def _run(command: list[str], *, timeout: float = 180) -> None:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"fixture command failed ({completed.returncode}): {' '.join(command)}\n{completed.stderr[-4000:]}"
        )


def find_ffmpeg() -> str:
    candidate = shutil.which("ffmpeg")
    if candidate:
        return candidate
    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).exists():
            return str(bundled)
    except (AttributeError, ImportError, OSError, RuntimeError):
        bundled = None
    raise RuntimeError("FFmpeg is required to generate the legal local test corpus")


def find_ffprobe(ffmpeg: str | None = None) -> str:
    candidate = shutil.which("ffprobe")
    if candidate:
        return candidate
    if ffmpeg:
        sibling = Path(ffmpeg).with_name("ffprobe")
        if sibling.exists():
            return str(sibling)
    raise RuntimeError("FFprobe is required by the engineering-quality harness")


def _generate_av(
    ffmpeg: str, path: Path, *, duration: int, size: str, video_kbps: int
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg,
            "-y",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={size}:rate=30:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=523.25:sample_rate=48000:duration={duration}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-b:v",
            f"{video_kbps}k",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            "-metadata",
            f"title={UNICODE_TITLE}",
            "-metadata",
            "comment=Harness-owned metadata: alpha, beta, gamma; <script>not executable</script>",
            str(path),
        ]
    )


def _generate_hls(
    ffmpeg: str, source: Path, root: Path, *, bandwidth: int, resolution: str
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    media = root / "media.m3u8"
    if not media.exists():
        _run(
            [
                ffmpeg,
                "-y",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-c",
                "copy",
                "-hls_time",
                "2",
                "-hls_playlist_type",
                "vod",
                "-hls_segment_filename",
                str(root / "segment-%03d.ts"),
                str(media),
            ]
        )
    master = root / "master.m3u8"
    master.write_text(
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        f'#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},AVERAGE-BANDWIDTH={bandwidth},RESOLUTION={resolution},FRAME-RATE=30.000,CODECS="avc1.42c01e,mp4a.40.2"\n'
        "media.m3u8\n",
        encoding="utf-8",
    )


def generate_fixtures(root: Path, *, deep: bool = False) -> dict[str, Any]:
    ffmpeg = find_ffmpeg()
    ffprobe = find_ffprobe(ffmpeg)
    root.mkdir(parents=True, exist_ok=True)
    short_path = root / "short-av.mp4"
    short_high_path = root / "short-high-av.mp4"
    long_path = root / "long-av.mp4"
    thumb_path = root / "thumbnail.jpg"
    if not short_path.exists():
        _generate_av(ffmpeg, short_path, duration=6, size="640x360", video_kbps=900)
    if not short_high_path.exists():
        _generate_av(
            ffmpeg,
            short_high_path,
            duration=6,
            size="960x540",
            video_kbps=1800,
        )
    if not long_path.exists():
        _generate_av(
            ffmpeg,
            long_path,
            duration=24 if not deep else 45,
            size="960x540",
            video_kbps=1800,
        )
    if not thumb_path.exists():
        _run(
            [
                ffmpeg,
                "-y",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x3634a3:s=640x360",
                "-frames:v",
                "1",
                str(thumb_path),
            ]
        )
    _generate_hls(
        ffmpeg,
        short_path,
        root / "hls-short",
        bandwidth=1_100_000,
        resolution="640x360",
    )
    _generate_hls(
        ffmpeg,
        short_high_path,
        root / "hls-short-high",
        bandwidth=2_100_000,
        resolution="960x540",
    )
    _generate_hls(
        ffmpeg, long_path, root / "hls-long", bandwidth=2_100_000, resolution="960x540"
    )
    multi_root = root / "hls-multi"
    multi_root.mkdir(parents=True, exist_ok=True)
    (multi_root / "master.m3u8").write_text(
        "#EXTM3U\n#EXT-X-VERSION:3\n"
        '#EXT-X-STREAM-INF:BANDWIDTH=1100000,AVERAGE-BANDWIDTH=1100000,RESOLUTION=640x360,FRAME-RATE=30.000,CODECS="avc1.42c01e,mp4a.40.2"\n'
        "../hls-short/media.m3u8\n"
        '#EXT-X-STREAM-INF:BANDWIDTH=2100000,AVERAGE-BANDWIDTH=2100000,RESOLUTION=960x540,FRAME-RATE=30.000,CODECS="avc1.42c01e,mp4a.40.2"\n'
        "../hls-short-high/media.m3u8\n",
        encoding="utf-8",
    )
    manifest = {
        "generator": "FFmpeg lavfi testsrc2+sine",
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "items": {
            "short-av": {
                "path": str(short_path),
                "sha256": sha256_file(short_path),
                "size_bytes": short_path.stat().st_size,
            },
            "short-high-av": {
                "path": str(short_high_path),
                "sha256": sha256_file(short_high_path),
                "size_bytes": short_high_path.stat().st_size,
            },
            "long-av": {
                "path": str(long_path),
                "sha256": sha256_file(long_path),
                "size_bytes": long_path.stat().st_size,
            },
            "thumbnail": {
                "path": str(thumb_path),
                "sha256": sha256_file(thumb_path),
                "size_bytes": thumb_path.stat().st_size,
            },
            "hls-short": {
                "path": str(root / "hls-short"),
                "segment_count": len(list((root / "hls-short").glob("*.ts"))),
            },
            "hls-multi": {
                "path": str(multi_root),
                "variant_count": 2,
                "resolutions": ["640x360", "960x540"],
            },
            "hls-long": {
                "path": str(root / "hls-long"),
                "segment_count": len(list((root / "hls-long").glob("*.ts"))),
            },
        },
    }
    (root / "generated-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest
