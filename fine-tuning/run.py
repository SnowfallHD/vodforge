"""Measure x264 and NVENC against identical decoded fixtures. No network access."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from fractions import Fraction
from itertools import pairwise
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yt_downloader.app import build_vod_ffmpeg_command, validate_output_artifact
from yt_downloader.export_planning import (
    build_auto_export_plan,
    export_mode_from_display_name,
)
from yt_downloader.models import OutputType


def run(command, *, cwd=None):
    result = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, timeout=600, check=False
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-6000:])
    return result.stdout


def probe(ffprobe, path):
    return json.loads(
        run(
            [
                ffprobe,
                "-v",
                "error",
                "-count_frames",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ]
        )
    )


def make_plan(name, metadata, preset, *, use_nvenc=False):
    video = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    fps = float(Fraction(video["avg_frame_rate"]))
    info = {
        "formats": [
            {
                "format_id": "video",
                "vcodec": "avc1",
                "acodec": "none",
                "width": video["width"],
                "height": video["height"],
                "fps": fps,
                "vbr": 500 if name == "static" else 4000,
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
    return build_auto_export_plan(
        info,
        mode=export_mode_from_display_name(preset),
        max_height=2160,
        use_nvenc=use_nvenc,
    )


def nvenc_candidate(command, cq, speed, aq="1", bframes=0):
    """Experimental overrides only; final verification uses production builder."""
    if not 1 <= cq <= 51:
        raise ValueError("Candidate CQ must be between 1 and 51")
    command = list(command)
    command[command.index("libx264")] = "h264_nvenc"
    command[command.index("-preset") + 1] = speed
    i = command.index("-crf:v:0")
    command[i : i + 2] = [
        "-rc:v:0",
        "vbr",
        "-cq:v:0",
        str(cq),
        "-b:v:0",
        "0",
        "-tune:v:0",
        "hq",
        "-rc-lookahead:v:0",
        "20",
        "-spatial-aq:v:0",
        "1" if aq == "1" else "0",
        "-temporal-aq:v:0",
        "1" if aq == "temporal" else "0",
        "-aq-strength:v:0",
        "8",
    ]
    command[-1:-1] = ["-bf:v:0", str(bframes), "-multipass:v:0", "fullres"]
    return command


def measure(ffmpeg, ffprobe, source, out, command, plan, root, duration, subsample=1):
    started = time.monotonic()
    run(command)
    seconds = time.monotonic() - started
    metadata = probe(ffprobe, out)
    output_video = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    reference = probe(ffprobe, source)
    reference_video = next(
        s for s in reference["streams"] if s["codec_type"] == "video"
    )
    if output_video["nb_read_frames"] != reference_video["nb_read_frames"]:
        raise RuntimeError(
            "Frame counts differ: normalize reference timing before comparing VMAF"
        )
    validate_output_artifact(
        out,
        OutputType.MP4,
        ffprobe,
        plan=plan,
        expected_duration_seconds=duration,
        ffprobe_data=metadata,
    )
    run([ffmpeg, "-v", "error", "-xerror", "-i", str(out), "-f", "null", "-"])
    quality = out.stem + "-vmaf.json"
    fps = plan.fps
    run(
        [
            ffmpeg,
            "-v",
            "error",
            "-threads",
            "4",
            "-i",
            str(out),
            "-threads",
            "4",
            "-i",
            str(source),
            "-lavfi",
            f"[0:v]settb=AVTB,setpts=N/({fps}*TB)[d];[1:v]settb=AVTB,setpts=N/({fps}*TB)[r];[d][r]libvmaf=log_fmt=json:log_path={quality}:n_threads=4:n_subsample={subsample}",
            "-an",
            "-f",
            "null",
            "-",
        ],
        cwd=root,
    )
    score = json.loads((root / quality).read_text())["pooled_metrics"]["vmaf"]
    frames = json.loads(
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
    times = [float(f["best_effort_timestamp_time"]) for f in frames] + [duration]
    maxgap = max(b - a for a, b in pairwise(times))
    if plan.keyframe_seconds and maxgap > plan.keyframe_seconds + 1 / fps + 0.01:
        raise RuntimeError(f"Keyframe contract failed: {maxgap}")
    video = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    return {
        "reference_frames": int(reference_video["nb_read_frames"]),
        "output_frames": int(output_video["nb_read_frames"]),
        "bytes": out.stat().st_size,
        "encode_seconds": round(seconds, 3),
        "vmaf": round(score["mean"], 3),
        "vmaf_min": round(score["min"], 3),
        "video_kbps": round(int(video["bit_rate"]) / 1000, 3),
        "keyframe_max_seconds": round(maxgap, 3),
        "validated": True,
        "full_decode": True,
        "output_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--ffprobe", required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stage", choices=["sweep", "verify"], default="sweep")
    parser.add_argument("--offsets", default="-3,-1,1")
    parser.add_argument("--speeds", default="p5,p6")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--encoders", choices=["cpu", "nvenc", "both"], default="both")
    parser.add_argument("--bframes", type=int, choices=[0, 3], default=0)
    parser.add_argument("--vmaf-subsample", type=int, default=1)
    parser.add_argument("--aq", default="1", choices=["0", "1", "temporal"])
    parser.add_argument("--names", default="ocean,static,motion60,grain")
    parser.add_argument("--presets", default="Everyday,Streaming,Editing,Sharing,CTV")
    args = parser.parse_args()
    if args.vmaf_subsample < 1:
        parser.error("--vmaf-subsample must be positive")
    if args.stage == "verify" and args.vmaf_subsample != 1:
        parser.error("Final verification requires full-frame VMAF")
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root / "results.json").exists():
        raise ValueError("Use a new output directory to preserve receipts")
    ffmpeg = str(Path(args.ffmpeg).resolve())
    ffprobe = str(Path(args.ffprobe).resolve())
    gpu = (
        run(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"]
        ).strip()
        if args.encoders != "cpu"
        else "not requested"
    )
    receipt = {
        "schema_version": 1,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "production_files": {
            name: hashlib.sha256(
                (
                    Path(__file__).resolve().parents[1] / "yt_downloader" / name
                ).read_bytes()
            ).hexdigest()
            for name in (
                "app.py",
                "models.py",
                "export_planning.py",
                "output_validation.py",
            )
        },
        "stage": args.stage,
        "vmaf_subsample": args.vmaf_subsample,
        "bframes": args.bframes,
        "platform": platform.platform(),
        "gpu": gpu,
        "python": platform.python_version(),
        "ffmpeg": run([ffmpeg, "-version"]).splitlines()[0],
        "source_commit": args.source_commit,
        "fixtures": {},
        "results": [],
    }
    for name in args.names.split(","):
        source = (args.fixtures / f"{name}.mkv").resolve()
        meta = probe(ffprobe, source)
        duration = float(meta["format"]["duration"])
        reference_video = next(s for s in meta["streams"] if s["codec_type"] == "video")
        if abs(float(reference_video.get("start_time", 0))) > 0.001:
            raise ValueError(
                "Reference video must start at zero; normalize PTS before calibration"
            )
        receipt["fixtures"][name] = {
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "duration": duration,
        }
        for preset in args.presets.split(","):
            plan = make_plan(name, meta, preset)
            configurations = [("cpu", None, None)]
            if args.stage == "sweep" and plan.video_crf is not None:
                configurations += [
                    ("nvenc", plan.video_crf + int(offset), speed)
                    for speed in args.speeds.split(",")
                    for offset in args.offsets.split(",")
                ]
            else:
                configurations += [("nvenc", None, None)]
            configurations = [
                c
                for c in configurations
                if args.encoders == "both" or c[0] == args.encoders
            ]
            for encoder, cq, speed in configurations:
                if args.stage == "verify":
                    plan = make_plan(name, meta, preset, use_nvenc=encoder == "nvenc")
                label = f"{name}-{preset}-{encoder}-{cq}-{speed}"
                out = root / f"{label}.mp4"
                command = build_vod_ffmpeg_command(
                    ffmpeg,
                    source,
                    out,
                    video_bitrate_kbps=plan.video_bitrate_kbps,
                    audio_bitrate_kbps=plan.audio_bitrate_kbps,
                    video_crf=plan.video_crf,
                    **({"nvenc_cq": plan.nvenc_cq} if args.stage == "verify" else {}),
                    keyframe_seconds=plan.keyframe_seconds,
                    fps=plan.fps,
                    constant_frame_rate=plan.constant_frame_rate,
                    video_maxrate_kbps=plan.video_maxrate_kbps,
                    use_nvenc=encoder == "nvenc" and cq is None,
                )
                if (
                    encoder == "nvenc"
                    and cq is None
                    and args.stage == "sweep"
                    and args.bframes
                ):
                    command[command.index("-preset") + 1] = args.speeds.split(",")[0]
                    command[-1:-1] = [
                        "-bf:v:0",
                        str(args.bframes),
                        "-rc-lookahead:v:0",
                        "20",
                        "-spatial-aq:v:0",
                        "1" if args.aq == "1" else "0",
                        "-temporal-aq:v:0",
                        "1" if args.aq == "temporal" else "0",
                        "-multipass:v:0",
                        "fullres",
                    ]
                if cq is not None:
                    command = nvenc_candidate(command, cq, speed, args.aq, args.bframes)
                if encoder == "nvenc" and "h264_nvenc" not in command:
                    raise RuntimeError("NVIDIA run resolved to a CPU encoder")
                result = {
                    "fixture": name,
                    "preset": preset,
                    "encoder": encoder,
                    "cq": plan.nvenc_cq if args.stage == "verify" else cq,
                    "speed": speed,
                    "spatial_aq": args.aq if cq is not None else None,
                    "crf": plan.video_crf,
                    **measure(
                        ffmpeg,
                        ffprobe,
                        source,
                        out,
                        command,
                        plan,
                        root,
                        duration,
                        args.vmaf_subsample,
                    ),
                }
                result["command"] = [
                    str(x)
                    .replace(str(root), "<output>")
                    .replace(str(args.fixtures.resolve()), "<fixtures>")
                    .replace(ffmpeg, "ffmpeg")
                    for x in command
                ]
                receipt["results"].append(result)
                (root / "results.json").write_text(json.dumps(receipt, indent=2) + "\n")
                print({k: v for k, v in result.items() if k != "command"}, flush=True)

    receipt["status"] = "complete"
    (root / "results.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
