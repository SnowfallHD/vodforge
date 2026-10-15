"""Observe cache retirement through real child processes, including failure."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("exit_code", [0, 7])
def test_build_cache_is_private_and_retired_without_touching_outputs(
    tmp_path, exit_code
):
    original = tmp_path / "retained-cache"
    original.mkdir()
    (original / "keep").write_text("retained")
    output = tmp_path / "package-receipt"
    runner = (
        Path(__file__).resolve().parents[1]
        / "scripts/run_with_ephemeral_pyinstaller_cache.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(runner),
            sys.executable,
            "-c",
            "import os,pathlib,sys; p=pathlib.Path(os.environ['PYINSTALLER_CONFIG_DIR']); "
            "(p/'transformed-binary').write_bytes(b'cache'); "
            "pathlib.Path(sys.argv[1]).write_text(str(p)); sys.exit(int(sys.argv[2]))",
            str(output),
            str(exit_code),
        ],
        env={**os.environ, "PYINSTALLER_CONFIG_DIR": str(original)},
        check=False,
    )
    assert result.returncode == exit_code
    assert not Path(output.read_text()).exists()
    assert (original / "keep").read_text() == "retained"
