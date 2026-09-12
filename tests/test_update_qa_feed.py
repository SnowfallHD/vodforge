"""Real loopback transport for isolated QA; installer verification stays separate."""

import hashlib
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from yt_downloader import updates


@pytest.fixture
def isolated_qa(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    home = root / "home"
    profile = home / "profile"
    temporary = root / "tmp"
    runtime = root / "runtime"
    for path in (profile, temporary, runtime):
        path.mkdir(parents=True)
    executable = root / "candidate" / "VODForge"
    executable.parent.mkdir()
    executable.touch()
    (runtime / "VODFORGE_TELEMETRY_POLICY").write_text("production")
    monkeypatch.setattr(updates.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updates.sys, "_MEIPASS", str(runtime), raising=False)
    monkeypatch.setattr(updates.sys, "executable", str(executable))
    for name, value in {
        "HOME": home,
        "USERPROFILE": home,
        "TMPDIR": temporary,
        "VODFORGE_QA_PROFILE": profile,
        "VODFORGE_QUALITY_E2E_ISOLATION_ROOT": root,
        "VODFORGE_QUALITY_E2E": "1",
        "VODFORGE_QA_PREVIEW_TELEMETRY": "1",
        "VODFORGE_QA_ACCESS_KEY": "a" * 64,
    }.items():
        monkeypatch.setenv(name, str(value))
    monkeypatch.delenv("VODFORGE_DISABLE_TELEMETRY", raising=False)
    return root


def test_normal_updater_has_no_qa_feed(monkeypatch):
    monkeypatch.delenv("VODFORGE_QA_UPDATE_FEED", raising=False)
    assert updates.qa_update_feed() is None


@pytest.mark.parametrize(
    "change",
    ["mode", "key", "disabled", "policy", "home", "executable"],
)
def test_qa_feed_requires_packaged_isolation(isolated_qa, monkeypatch, change):
    monkeypatch.setenv(
        "VODFORGE_QA_UPDATE_FEED",
        "http://127.0.0.1:12345/" + "b" * 32 + "/release.json",
    )
    if change == "mode":
        monkeypatch.delenv("VODFORGE_QUALITY_E2E")
    elif change == "key":
        monkeypatch.setenv("VODFORGE_QA_ACCESS_KEY", "invalid")
    elif change == "disabled":
        monkeypatch.setenv("VODFORGE_DISABLE_TELEMETRY", "1")
    elif change == "policy":
        (isolated_qa / "runtime/VODFORGE_TELEMETRY_POLICY").write_text("disabled")
    elif change == "home":
        monkeypatch.setenv("HOME", str(isolated_qa))
        monkeypatch.setenv("USERPROFILE", str(isolated_qa))
    else:
        monkeypatch.setattr(updates.sys, "executable", str(isolated_qa.parent))
    with pytest.raises(ValueError, match="isolated preview"):
        updates.qa_update_feed()


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/release.json",
        "http://localhost:12345/" + "b" * 32 + "/release.json",
        "http://127.0.0.1:12345/release.json",
        "http://user@127.0.0.1:12345/" + "b" * 32 + "/release.json",
        "http://127.0.0.1:12345/" + "b" * 32 + "/release.json?extra=1",
        "file:///tmp/release.json",
    ],
)
def test_qa_feed_refuses_other_authorities(isolated_qa, monkeypatch, url):
    monkeypatch.setenv("VODFORGE_QA_UPDATE_FEED", url)
    with pytest.raises(ValueError, match="scoped loopback"):
        updates.qa_update_feed()


@pytest.mark.parametrize("fault", [None, "checksum", "redirect", "asset_escape"])
@pytest.mark.parametrize("entrypoint", ["app", "detached_repair"])
def test_real_qa_feed_download(isolated_qa, monkeypatch, fault, entrypoint):
    powershell = os.environ.get("VODFORGE_QA_POWERSHELL")
    if entrypoint == "detached_repair" and not powershell:
        if sys.platform != "win32":
            pytest.skip("requires PowerShell runtime")
        powershell = "powershell.exe"
    content = b"bounded transport fixture, not an installer"
    name = "VODForge-Windows-Setup-v1.2.3.exe"
    requests = []
    routes = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            if fault == "redirect" and self.path.endswith("release.json"):
                self.send_response(302)
                self.send_header("Location", "/must-not-be-requested")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(routes[self.path])

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    token = "/" + "b" * 32 + "/"
    base = f"http://127.0.0.1:{server.server_port}{token}"
    payload = {
        "tag_name": "v1.2.3",
        "html_url": "https://github.com/SnowfallHD/vodforge/releases",
        "assets": [
            {
                "name": n,
                "browser_download_url": base + "v1.2.3/" + n,
                "size": len(content),
            }
            for n in (name, "SHA256SUMS.txt")
        ],
    }
    if fault == "asset_escape":
        payload["assets"][0]["browser_download_url"] = "https://example.com/installer"
    digest = "0" * 64 if fault == "checksum" else hashlib.sha256(content).hexdigest()
    routes[token + "release.json"] = json.dumps(payload).encode()
    routes[token + "v1.2.3/SHA256SUMS.txt"] = f"{digest}  {name}\n".encode()
    routes[token + "v1.2.3/" + name] = content
    monkeypatch.setenv("VODFORGE_QA_UPDATE_FEED", base + "release.json")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    destination = isolated_qa / "downloads"
    try:
        if entrypoint == "detached_repair":
            from yt_downloader.windows_update_recovery import RECOVERY_FUNCTIONS

            destination.mkdir()
            script = isolated_qa / "repair.ps1"
            escaped = str(destination).replace("'", "''")
            script.write_text(
                RECOVERY_FUNCTIONS + f"\n$ErrorActionPreference='Stop'\n"
                f"try {{ Get-VODForgeRepairInstaller '{escaped}' '{base}release.json' | Out-Null }}\n"
                "catch { Write-Output $_.Exception.Message; exit 1 }\n"
            )
            result = subprocess.run(
                [powershell, "-NoProfile", "-File", str(script)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            assert (result.returncode == 0) == (fault is None), (
                result.stdout + result.stderr
            )
            if fault is None:
                assert (destination / name).read_bytes() == content
            else:
                assert not list(destination.glob("*"))
            assert "/must-not-be-requested" not in requests
            return
        if fault:
            with pytest.raises((ValueError, RuntimeError)):
                release = updates.fetch_latest_release()
                updates.download_verified_update(
                    release, destination, platform_name="win32"
                )
            assert not list(destination.glob("*"))
        else:
            release = updates.fetch_latest_release()
            path = updates.download_verified_update(
                release, destination, platform_name="win32"
            )
            assert path.read_bytes() == content
            assert len(requests) == 3
        assert "/must-not-be-requested" not in requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
