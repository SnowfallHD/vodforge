from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate short offline VODForge playback fixtures."
    )
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    ffmpeg = args.ffmpeg.expanduser().resolve(strict=True)
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    common = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y"]

    for filename, size, rate in (
        ("vodforge_720p24.mp4", "1280x720", "24"),
        ("vodforge_1080p60.mp4", "1920x1080", "60"),
    ):
        _run(
            [
                *common,
                "-f",
                "lavfi",
                "-i",
                f"testsrc2=size={size}:rate={rate}",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000",
                "-t",
                "5",
                "-shortest",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(output / filename),
            ]
        )

    _run(
        [
            *common,
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=523.25:sample_rate=48000",
            "-t",
            "5",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(output / "vodforge_audio.mp3"),
        ]
    )


if __name__ == "__main__":
    main()
