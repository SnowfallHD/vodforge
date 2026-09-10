"""Bounded, offline preset comparison using the same encoder as the app.

Writes fixtures, real exports and quality/size/timing receipts to --output.
VMAF compares each export with its decoded source; it is not an absolute
assessment of the source, device certification, or an ingest acceptance test.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from fractions import Fraction
from itertools import pairwise
from pathlib import Path


def run(args: list[str], timeout: int = 300) -> str:
    return subprocess.run(
        args, check=True, capture_output=True, text=True, timeout=timeout
    ).stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--ffprobe", required=True)
    parser.add_argument("--ocean", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path)
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    ffmpeg = str(Path(args.ffmpeg).resolve())
    ffprobe = str(Path(args.ffprobe).resolve())
    base = [ffmpeg, "-y", "-nostdin", "-v", "error"]
    fixtures = {
        "ocean": ["-i", str(args.ocean.resolve())],
        "static": [
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=1920x1080:rate=30,select='eq(n,0)',loop=loop=-1:size=1:start=0,setpts=N/30/TB",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
        ],
        "motion60": [
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=60",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=523:sample_rate=48000",
        ],
        "grain": [
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=24,noise=alls=12:allf=t+u:all_seed=42",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=330:sample_rate=48000,volume=0.0001",
        ],
    }
    candidates = {
        "Everyday": (21, 5),
        "Streaming": (20, 2),
        "Editing": (18, 1),
        "Sharing": (25, 5),
        "CTV": (None, 2),
        "Custom": (None, 0),
    }
    receipts = []
    for name, inputs in fixtures.items():
        source = (args.fixtures.resolve() if args.fixtures else root) / f"{name}.mkv"
        if not source.exists():
            run(
                [
                    *base,
                    *inputs,
                    "-t",
                    "6",
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0" if name == "ocean" else "1:a:0",
                    "-c:v",
                    "ffv1",
                    "-level",
                    "3",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "pcm_s16le",
                    "-ac",
                    "2",
                    str(source),
                ]
            )
        probe = json.loads(
            run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(source),
                ]
            )
        )
        v = next(s for s in probe["streams"] if s["codec_type"] == "video")
        fps = float(Fraction(v["avg_frame_rate"]))
        for preset, (crf, interval) in candidates.items():
            out = root / f"{name}-{preset}.mp4"
            bitrate = 5000 if name == "ocean" else (2000 if name == "static" else 5000)
            if preset == "Custom":
                bitrate = 10000
            audio = {
                "Everyday": 160,
                "Streaming": 192,
                "Editing": 192,
                "Sharing": 128,
                "CTV": 160,
                "Custom": 320,
            }[preset]
            rate = (
                ["-crf", str(crf)]
                if crf is not None
                else [
                    "-b:v",
                    f"{bitrate}k",
                    "-minrate",
                    f"{bitrate}k",
                    "-maxrate",
                    f"{bitrate}k",
                    "-bufsize",
                    f"{bitrate * 2}k",
                    "-x264-params",
                    "nal-hrd=cbr:force-cfr=1",
                ]
            )
            key = ["-g", str(round(fps * interval))] if interval else []
            command = [
                *base,
                "-i",
                str(source),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-threads",
                "4",
                *rate,
                *key,
                "-pix_fmt",
                "yuv420p",
                "-profile:v",
                "high",
                "-c:a",
                "aac",
                "-b:a",
                f"{audio}k",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-movflags",
                "+faststart",
                str(out),
            ]
            plan = None
            if args.production:
                from yt_downloader.app import build_vod_ffmpeg_command
                from yt_downloader.export_planning import (
                    apply_manual_export_settings,
                    build_auto_export_plan,
                    export_mode_from_display_name,
                )
                from yt_downloader.models import ManualExportSettings

                # Synthetic hints model an ordinary compressed input. VMAF
                # references remain the deterministic lossless fixture frames.
                source_rate = {
                    "ocean": 4000,
                    "static": 500,
                    "motion60": 4000,
                    "grain": 4000,
                }[name]
                info = {
                    "formats": [
                        {
                            "format_id": "video",
                            "vcodec": "avc1",
                            "acodec": "none",
                            "width": v["width"],
                            "height": v["height"],
                            "fps": fps,
                            "vbr": source_rate,
                            "ext": "mp4",
                        },
                        {
                            "format_id": "audio",
                            "vcodec": "none",
                            "acodec": "mp4a.40.2",
                            "abr": 130,
                            "ext": "m4a",
                        },
                    ]
                }
                plan = build_auto_export_plan(
                    info, mode=export_mode_from_display_name(preset), max_height=2160
                )
                if preset == "Custom":
                    plan = apply_manual_export_settings(plan, ManualExportSettings())
                crf = plan.video_crf
                command = build_vod_ffmpeg_command(
                    ffmpeg,
                    source,
                    out,
                    video_bitrate_kbps=plan.video_bitrate_kbps,
                    audio_bitrate_kbps=plan.audio_bitrate_kbps,
                    x264_preset=plan.x264_preset,
                    video_crf=plan.video_crf,
                    keyframe_seconds=plan.keyframe_seconds,
                    fps=plan.fps,
                    constant_frame_rate=plan.constant_frame_rate,
                    video_maxrate_kbps=plan.video_maxrate_kbps,
                )
            started = time.monotonic()
            run(command)
            seconds = time.monotonic() - started
            output_probe = json.loads(
                run(
                    [
                        ffprobe,
                        "-v",
                        "error",
                        "-show_streams",
                        "-show_format",
                        "-of",
                        "json",
                        str(out),
                    ]
                )
            )
            if plan is not None:
                from yt_downloader.app import validate_output_artifact
                from yt_downloader.models import OutputType

                validate_output_artifact(
                    out,
                    OutputType.MP4,
                    ffprobe,
                    plan=plan,
                    expected_duration_seconds=6,
                    ffprobe_data=output_probe,
                )
            run([*base, "-xerror", "-i", str(out), "-f", "null", "-"])
            keyframes = json.loads(
                run(
                    [
                        ffprobe,
                        "-v",
                        "error",
                        "-select_streams",
                        "v:0",
                        "-skip_frame",
                        "nokey",
                        "-show_frames",
                        "-show_entries",
                        "frame=best_effort_timestamp_time",
                        "-of",
                        "json",
                        str(out),
                    ]
                )
            )["frames"]
            key_times = [float(f["best_effort_timestamp_time"]) for f in keyframes]
            max_gap = max([b - a for a, b in pairwise(key_times)] + [6 - key_times[-1]])
            quality = root / f"{name}-{preset}-vmaf.json"
            run(
                [
                    *base,
                    "-i",
                    str(out),
                    "-i",
                    str(source),
                    "-lavfi",
                    f"[0:v]settb=AVTB,setpts=N/({fps}*TB)[d];[1:v]settb=AVTB,setpts=N/({fps}*TB)[r];[d][r]libvmaf=log_fmt=json:log_path={quality}:n_threads=4",
                    "-an",
                    "-f",
                    "null",
                    "-",
                ]
            )
            score = json.loads(quality.read_text())["pooled_metrics"]["vmaf"]["mean"]
            result = {
                "fixture": name,
                "preset": preset,
                "crf": crf,
                "bytes": out.stat().st_size,
                "encode_seconds": round(seconds, 3),
                "vmaf": round(score, 3),
                "keyframe_max_seconds": round(max_gap, 3),
                "video_kbps": round(
                    int(
                        next(
                            s
                            for s in output_probe["streams"]
                            if s["codec_type"] == "video"
                        )["bit_rate"]
                    )
                    / 1000,
                    3,
                ),
                "validated": plan is not None,
                "command": command,
            }
            receipts.append(result)
            (root / "results.json").write_text(json.dumps(receipts, indent=2) + "\n")
            print({k: val for k, val in result.items() if k != "command"}, flush=True)


if __name__ == "__main__":
    main()
