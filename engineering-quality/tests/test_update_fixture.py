"""Exercise the real QA feed process; never execute the transport-only artifact."""

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


def test_update_fixture_serves_only_declared_bytes_and_retains_faults(tmp_path):
    artifact = tmp_path / "VODForge-Windows-Setup-v1.2.3.exe"
    artifact.write_bytes(b"transport fixture, not an executable")
    output = tmp_path / "feed"
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ, PYTHONPATH=str(root / "engineering-quality"))
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "quality_harness.update_fixture",
            "--version",
            "1.2.3",
            "--asset",
            str(artifact),
            "--output",
            str(output),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while (
            not (output / "feed.json").exists()
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert (output / "feed.json").exists()
        feed = json.loads((output / "feed.json").read_text())
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(feed["url"], timeout=3) as response:
            release = json.load(response)
        assets = {a["name"]: a["browser_download_url"] for a in release["assets"]}
        with opener.open(assets[artifact.name], timeout=3) as response:
            assert response.read() == artifact.read_bytes()
        with opener.open(assets["SHA256SUMS.txt"], timeout=3) as response:
            assert (
                hashlib.sha256(artifact.read_bytes()).hexdigest().encode()
                in response.read()
            )
        with pytest.raises(urllib.error.HTTPError) as failure:
            opener.open(feed["url"] + "?escape=1", timeout=3)
        assert failure.value.code == 404
        (output / "unavailable").touch()
        with pytest.raises(urllib.error.HTTPError) as failure:
            opener.open(feed["url"], timeout=3)
        assert failure.value.code == 503
        (output / "unavailable").unlink()
        artifact.write_bytes(b"changed")
        with pytest.raises(urllib.error.HTTPError) as failure:
            opener.open(assets[artifact.name], timeout=3)
        assert failure.value.code == 409
        assert [
            json.loads(line)["status"]
            for line in (output / "requests.jsonl").read_text().splitlines()
        ] == [200, 200, 200, 404, 503, 409]
    finally:
        process.terminate()
        process.communicate(timeout=10)
