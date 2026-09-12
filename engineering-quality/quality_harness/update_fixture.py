"""Serve fixed release artifacts over loopback for isolated packaged update QA.

This is an offline harness fixture, not a publication endpoint. The app still
verifies hashes, publisher signatures, installed version and relaunch identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer


class _LoopbackUpdateServer(ThreadingHTTPServer):
    def server_bind(self) -> None:
        # HTTPServer normally reverse-resolves its address. The fixed loopback
        # fixture needs no DNS, which can stall in isolated CI environments.
        TCPServer.server_bind(self)
        self.server_name = "127.0.0.1"
        self.server_port = self.server_address[1]


def serve(version: str, assets: list[Path], output: Path) -> None:
    if re.fullmatch(r"\d+\.\d+\.\d+", version) is None:
        raise ValueError("A stable numeric fixture version is required")
    accepted = {
        f"VODForge-Windows-Setup-v{version}.exe",
        f"VODForge-macOS-arm64-v{version}.zip",
        f"VODForge-macOS-x64-v{version}.zip",
    }
    files = {path.name: path.resolve(strict=True) for path in assets}
    if not files or len(files) != len(assets) or not files.keys() <= accepted:
        raise ValueError("Supply unique final installer/app archives for this version")
    facts = {}
    for name, path in files.items():
        if not path.is_file() or not 0 < path.stat().st_size <= 4 * 1024**3:
            raise ValueError("Invalid fixture artifact")
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        facts[name] = {
            "sha256": digest,
            "size": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
        }
    checksums = "".join(
        f"{facts[name]['sha256']}  {name}\n" for name in sorted(files)
    ).encode()
    prefix = "/" + uuid.uuid4().hex + "/"
    tag = "v" + version
    output.mkdir(parents=True, exist_ok=False)
    ledger = output / "requests.jsonl"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, body, path = 404, b"not found", None
            if (output / "unavailable").exists() and self.path.startswith(prefix):
                status, body = 503, b"QA update fixture temporarily unavailable"
            elif self.path == prefix + "release.json":
                status = 200
                body = json.dumps(
                    {
                        "tag_name": tag,
                        "draft": False,
                        "prerelease": False,
                        "name": "Isolated QA release " + version,
                        "body": "Local signed-artifact QA fixture; not a public release.",
                        "html_url": "https://github.com/SnowfallHD/vodforge/releases",
                        "assets": [
                            {
                                "name": name,
                                "size": size,
                                "browser_download_url": base + tag + "/" + name,
                            }
                            for name, size in [(n, facts[n]["size"]) for n in files]
                            + [("SHA256SUMS.txt", len(checksums))]
                        ],
                    }
                ).encode()
            elif self.path == prefix + tag + "/SHA256SUMS.txt":
                status, body = 200, checksums
            else:
                for name, candidate in files.items():
                    if self.path == prefix + tag + "/" + name:
                        stat = candidate.stat()
                        if (
                            stat.st_size == facts[name]["size"]
                            and stat.st_mtime_ns == facts[name]["mtime_ns"]
                        ):
                            status, path = 200, candidate
                        else:
                            status, body = 409, b"Fixture artifact changed"
            with ledger.open("a") as handle:
                handle.write(json.dumps({"path": self.path, "status": status}) + "\n")
            self.send_response(status)
            self.send_header(
                "Content-Length", str(path.stat().st_size if path else len(body))
            )
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            try:
                if path:
                    with path.open("rb") as source:
                        shutil.copyfileobj(source, self.wfile)
                else:
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_args):
            pass

    server = _LoopbackUpdateServer(("127.0.0.1", 0), Handler)
    base = f"http://127.0.0.1:{server.server_port}{prefix}"
    (output / "feed.json").write_text(
        json.dumps(
            {"url": base + "release.json", "version": version, "assets": facts},
            indent=2,
        )
    )
    print(f"QA update feed: {output / 'feed.json'}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--asset", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    serve(args.version, args.asset, args.output)


if __name__ == "__main__":
    main()
