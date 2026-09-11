"""Guard against misleading calibration receipts and command substitution."""

import importlib.util
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "fine_tuning_runner", Path(__file__).parents[1] / "run.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_search_does_not_mutate_cpu_reference_command():
    source = [
        "ffmpeg",
        "-i",
        "source with spaces.mkv",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf:v:0",
        "21",
        "-maxrate",
        "10000k",
        "output.mp4",
    ]
    original = list(source)
    gpu = runner.nvenc_candidate(source, 24, "p6", "temporal", 3)
    assert source == original
    assert gpu[gpu.index("-i") + 1] == "source with spaces.mkv"
    assert gpu[gpu.index("-maxrate") + 1] == "10000k"
    assert "h264_nvenc" in gpu and "libx264" not in gpu and "-crf:v:0" not in gpu
    assert gpu[gpu.index("-cq:v:0") + 1] == "24"


def test_final_verification_refuses_sampled_quality_scores(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            "--ffmpeg",
            "ffmpeg",
            "--ffprobe",
            "ffprobe",
            "--fixtures",
            str(tmp_path),
            "--output",
            str(tmp_path / "out"),
            "--source-commit",
            "test",
            "--stage",
            "verify",
            "--vmaf-subsample",
            "4",
        ],
    )
    with pytest.raises(SystemExit) as result:
        runner.main()
    assert result.value.code == 2
    assert not (tmp_path / "out").exists()


def test_existing_receipts_cannot_be_replaced(monkeypatch, tmp_path):
    receipt = tmp_path / "results.json"
    receipt.write_text("prior evidence")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            "--ffmpeg",
            "ffmpeg",
            "--ffprobe",
            "ffprobe",
            "--fixtures",
            str(tmp_path),
            "--output",
            str(tmp_path),
            "--source-commit",
            "test",
        ],
    )
    with pytest.raises(ValueError, match="preserve receipts"):
        runner.main()
    assert receipt.read_text() == "prior evidence"


def test_real_offset_reference_is_rejected_before_scoring(monkeypatch, tmp_path):
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("requires FFmpeg and ffprobe")
    source = tmp_path / "offset.mkv"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x90:rate=30",
            "-t",
            "0.2",
            "-c:v",
            "ffv1",
            "-output_ts_offset",
            "0.021",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            "--ffmpeg",
            ffmpeg,
            "--ffprobe",
            ffprobe,
            "--fixtures",
            str(tmp_path),
            "--output",
            str(tmp_path / "out"),
            "--source-commit",
            "test",
            "--stage",
            "verify",
            "--encoders",
            "cpu",
            "--names",
            "offset",
            "--presets",
            "Everyday",
        ],
    )
    with pytest.raises(ValueError, match="Reference video must start at zero"):
        runner.main()
    assert not (tmp_path / "out" / "results.json").exists()
