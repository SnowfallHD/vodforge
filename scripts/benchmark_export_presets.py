"""Compatibility entry point; preset experiments now live in fine-tuning."""

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "fine-tuning/benchmark_export_presets.py"
        ),
        run_name="__main__",
    )
