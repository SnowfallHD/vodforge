"""Real provider stream-copy probe; run with PYTHONPATH=.:engineering-quality.

Codec filtering simulates each supported available-source family. Downloads,
packaging, validation and packet comparisons use the real production pipeline.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

os.environ["VODFORGE_DISABLE_TELEMETRY"] = "1"
from quality_harness import pipeline

import yt_downloader.app as app_module

root = Path("build/original-audio-verification").resolve()
root.mkdir(parents=True, exist_ok=True)
pipeline.configure_production_sandbox(root)
runner = pipeline.HeadlessPipelineRunner(root)
build_job = pipeline.build_job
build_plan = app_module.build_original_audio_plan
build_options = app_module.DownloaderApp._build_ydl_options
rows = []
for codec in ("opus", "mp4a"):
    source = root / (codec + "-source.bin")

    def job_factory(**kwargs):
        job = build_job(**kwargs)
        job.single_video_only = True
        return job

    def plan_factory(info, codec=codec):
        return build_plan(
            {
                **info,
                "formats": [
                    f
                    for f in info["formats"]
                    if str(f.get("acodec", "")).startswith(codec)
                ],
            }
        )

    def options_factory(self, *args, source=source, **kwargs):
        options = build_options(self, *args, **kwargs)

        def capture(event):
            if event.get("status") == "finished":
                shutil.copyfile(event["filename"], source)

        options["progress_hooks"] = [*options.get("progress_hooks", []), capture]
        return options

    with (
        patch.object(pipeline, "build_job", job_factory),
        patch.object(app_module, "build_original_audio_plan", plan_factory),
        patch.object(app_module.DownloaderApp, "_build_ydl_options", options_factory),
    ):
        result = runner.run_job(
            case_id=codec,
            url="https://www.youtube.com/watch?v=8mv2Gonsdog",
            output_type="Original audio",
            re_raise=False,
        )
    media = [
        Path(o["path"])
        for o in result["outputs"]
        if Path(o["path"]).suffix in (".opus", ".m4a")
    ]
    row = {
        "codec": codec,
        "outcome": result["outcome"],
        "error": result["error"],
        "media_count": len(media),
        "survivors": result["active_children_before_harness_cleanup"],
        "staging": result["staging_entries_after"],
    }
    if source.exists() and len(media) == 1:

        def packets(path):
            data = subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_packets",
                    "-show_data_hash",
                    "sha256",
                    "-of",
                    "json",
                    str(path),
                ]
            )
            return [p["data_hash"] for p in json.loads(data)["packets"]]

        original = packets(source)
        exported = packets(media[0])
        row["packets"] = len(original)
        row["packet_payloads_identical"] = bool(original) and original == exported
        decoded = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(media[0]), "-f", "null", "-"],
            capture_output=True,
            text=True,
            check=False,
        )
        row["decode_returncode"] = decoded.returncode
        row["decode_errors"] = decoded.stderr
    rows.append(row)
    (root / "receipt.json").write_text(json.dumps(rows, indent=2))
    print(json.dumps(row), flush=True)
    if (
        row.get("packet_payloads_identical") is not True
        or row.get("decode_returncode") != 0
        or row["error"]
        or row["survivors"]
        or row["staging"]
    ):
        raise SystemExit("Audio verification failed")
