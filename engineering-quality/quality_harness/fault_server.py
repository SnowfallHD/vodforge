from __future__ import annotations

import html
import socket
import threading
import time
import urllib.parse
from collections import Counter
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Self

from .fixtures import UNICODE_TITLE


class FaultState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.requests: Counter[str] = Counter()
        self.statuses: Counter[str] = Counter()
        self.bytes_sent: Counter[str] = Counter()
        self.retry_failures_remaining = 2
        self.interruptions_remaining = 1
        self.interruptions_injected = 0

    def record_request(self, route: str) -> None:
        with self.lock:
            self.requests[route] += 1

    def record_status(self, status: int) -> None:
        with self.lock:
            self.statuses[str(status)] += 1

    def record_bytes(self, route: str, size: int) -> None:
        with self.lock:
            self.bytes_sent[route] += size

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "requests": dict(self.requests),
                "statuses": dict(self.statuses),
                "bytes_sent": dict(self.bytes_sent),
                "total_requests": sum(self.requests.values()),
                "total_bytes_sent": sum(self.bytes_sent.values()),
                "interruptions_injected": self.interruptions_injected,
            }


class FixtureHTTPServer:
    def __init__(self, fixture_dir: Path) -> None:
        self.fixture_dir = fixture_dir
        self.state = FaultState()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("fixture server has not started")
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def start(self) -> FixtureHTTPServer:
        fixture_dir = self.fixture_dir
        state = self.state

        class Handler(BaseHTTPRequestHandler):
            server_version = "VODForgeQualityOrigin/1.0"
            protocol_version = "HTTP/1.1"

            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def do_HEAD(self) -> None:
                self._dispatch(send_body=False)

            def do_GET(self) -> None:
                self._dispatch(send_body=True)

            def _dispatch(self, *, send_body: bool) -> None:
                route = urllib.parse.urlsplit(self.path).path
                state.record_request(route)
                if route == "/health":
                    self._bytes_response(
                        b"ok\n", "text/plain; charset=utf-8", send_body=send_body
                    )
                    return
                if route == "/status/404":
                    self._bytes_response(
                        b"not found\n",
                        "text/plain; charset=utf-8",
                        status=404,
                        send_body=send_body,
                    )
                    return
                if route == "/status/500":
                    self._bytes_response(
                        b"injected server error\n",
                        "text/plain; charset=utf-8",
                        status=500,
                        send_body=send_body,
                    )
                    return
                if route == "/fault/retry/page":
                    with state.lock:
                        should_fail = state.retry_failures_remaining > 0
                        if should_fail:
                            state.retry_failures_remaining -= 1
                    if should_fail:
                        self._bytes_response(
                            b"retry later\n",
                            "text/plain; charset=utf-8",
                            status=503,
                            headers={"Retry-After": "0"},
                            send_body=send_body,
                        )
                        return
                    self._page_response(send_body=send_body)
                    return
                if route in {
                    "/page/unicode",
                    "/page/normal",
                    "/page/long",
                    "/page/multi",
                    "/slow/page",
                    "/fault/interrupt/page",
                }:
                    self._page_response(
                        slow=route.startswith("/slow/"),
                        long=route == "/page/long",
                        multi=route == "/page/multi",
                        interrupt=route == "/fault/interrupt/page",
                        send_body=send_body,
                    )
                    return
                if route.startswith(("/hls/", "/slow/hls/", "/fault/interrupt/hls/")):
                    self._hls_response(route, send_body=send_body)
                    return
                if route == "/thumbnail.jpg":
                    self._file_response(
                        fixture_dir / "thumbnail.jpg",
                        route,
                        "image/jpeg",
                        send_body=send_body,
                    )
                    return
                if route in {"/media/short-av.mp4", "/slow/media/short-av.mp4"}:
                    self._file_response(
                        fixture_dir / "short-av.mp4",
                        route,
                        "video/mp4",
                        slow=route.startswith("/slow/"),
                        send_body=send_body,
                    )
                    return
                if route in {
                    "/media/long-av.mp4",
                    "/slow/media/long-av.mp4",
                    "/fault/interrupt/media/long-av.mp4",
                }:
                    self._file_response(
                        fixture_dir / "long-av.mp4",
                        route,
                        "video/mp4",
                        slow=route.startswith("/slow/"),
                        interrupt=route.startswith("/fault/interrupt/"),
                        send_body=send_body,
                    )
                    return
                self._bytes_response(
                    b"unknown harness route\n",
                    "text/plain; charset=utf-8",
                    status=404,
                    send_body=send_body,
                )

            def _page_response(
                self,
                *,
                slow: bool = False,
                long: bool = False,
                multi: bool = False,
                interrupt: bool = False,
                send_body: bool,
            ) -> None:
                if interrupt:
                    media = "/fault/interrupt/hls/hls-long/master.m3u8"
                elif slow:
                    media = "/slow/hls/hls-long/master.m3u8"
                elif long:
                    media = "/hls/hls-long/master.m3u8"
                elif multi:
                    media = "/hls/hls-multi/master.m3u8"
                else:
                    media = "/hls/hls-short/master.m3u8"
                document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(UNICODE_TITLE)}</title>
  <meta name="description" content="Synthetic metadata-rich VODForge fixture; safe, local, and deterministic.">
  <meta name="keywords" content="quality, reliability, unicode, punctuation, harness">
  <meta property="og:title" content="{html.escape(UNICODE_TITLE)}">
  <meta property="og:description" content="Synthetic metadata-rich VODForge fixture with a thumbnail and tags.">
  <meta property="og:image" content="{self._origin()}/thumbnail.jpg">
  <meta property="og:video" content="{self._origin()}{media}">
  <meta property="og:video:type" content="application/x-mpegURL">
</head>
<body><video controls src="{media}" poster="/thumbnail.jpg"></video></body>
</html>
""".encode()
                self._bytes_response(
                    document, "text/html; charset=utf-8", send_body=send_body
                )

            def _hls_response(self, route: str, *, send_body: bool) -> None:
                slow = route.startswith("/slow/")
                interrupt = route.startswith("/fault/interrupt/")
                relative = (
                    route.removeprefix("/slow/")
                    .removeprefix("/fault/interrupt/")
                    .removeprefix("/")
                )
                # URL path hls/hls-short/... maps directly below fixture_dir.
                parts = relative.split("/")
                if len(parts) < 3 or parts[0] != "hls":
                    self._bytes_response(
                        b"bad hls route\n",
                        "text/plain",
                        status=404,
                        send_body=send_body,
                    )
                    return
                path = fixture_dir.joinpath(*parts[1:])
                if path.suffix == ".m3u8":
                    if not path.is_file():
                        self._bytes_response(
                            b"playlist missing\n",
                            "text/plain",
                            status=404,
                            send_body=send_body,
                        )
                        return
                    body = path.read_text(encoding="utf-8")
                    if slow or interrupt:
                        prefix_root = "/slow/hls" if slow else "/fault/interrupt/hls"
                        prefix = f"{prefix_root}/{parts[1]}/"
                        rewritten = []
                        for line in body.splitlines():
                            rewritten.append(
                                prefix + line
                                if line and not line.startswith("#")
                                else line
                            )
                        body = "\n".join(rewritten) + "\n"
                    self._bytes_response(
                        body.encode("utf-8"),
                        "application/vnd.apple.mpegurl",
                        send_body=send_body,
                    )
                    return
                self._file_response(
                    path,
                    route,
                    "video/mp2t",
                    slow=slow,
                    interrupt=interrupt,
                    send_body=send_body,
                )

            def _origin(self) -> str:
                host = (
                    self.headers.get("Host")
                    or f"127.0.0.1:{self.server.server_address[1]}"
                )
                return f"http://{host}"

            def _bytes_response(
                self,
                body: bytes,
                content_type: str,
                *,
                status: int = 200,
                headers: dict[str, str] | None = None,
                send_body: bool,
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self.end_headers()
                state.record_status(status)
                if send_body:
                    try:
                        self.wfile.write(body)
                        self.wfile.flush()
                        state.record_bytes(
                            urllib.parse.urlsplit(self.path).path, len(body)
                        )
                    except (BrokenPipeError, ConnectionResetError):
                        pass

            def _file_response(
                self,
                path: Path,
                route: str,
                content_type: str,
                *,
                slow: bool = False,
                interrupt: bool = False,
                send_body: bool,
            ) -> None:
                if not path.is_file():
                    self._bytes_response(
                        b"fixture missing\n",
                        "text/plain",
                        status=500,
                        send_body=send_body,
                    )
                    return
                size = path.stat().st_size
                start = 0
                end = size - 1
                range_header = self.headers.get("Range") or ""
                if range_header.startswith("bytes="):
                    raw = range_header[6:].split(",", 1)[0]
                    left, _, right = raw.partition("-")
                    try:
                        if left:
                            start = min(int(left), size - 1)
                        if right:
                            end = min(int(right), size - 1)
                    except ValueError:
                        self._bytes_response(
                            b"bad range\n",
                            "text/plain",
                            status=416,
                            send_body=send_body,
                        )
                        return
                length = max(0, end - start + 1)
                status = HTTPStatus.PARTIAL_CONTENT if range_header else HTTPStatus.OK
                should_interrupt = False
                if interrupt and send_body:
                    with state.lock:
                        should_interrupt = state.interruptions_remaining > 0
                        if should_interrupt:
                            state.interruptions_remaining -= 1
                            state.interruptions_injected += 1
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(length))
                if status == HTTPStatus.PARTIAL_CONTENT:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Connection", "close")
                self.end_headers()
                state.record_status(int(status))
                if not send_body:
                    return
                remaining = length
                sent = 0
                interrupt_after = max(1, length // 3)
                try:
                    with path.open("rb") as handle:
                        handle.seek(start)
                        while remaining > 0:
                            chunk = handle.read(min(16 * 1024, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            self.wfile.flush()
                            remaining -= len(chunk)
                            sent += len(chunk)
                            state.record_bytes(route, len(chunk))
                            if should_interrupt and sent >= interrupt_after:
                                try:
                                    self.connection.shutdown(socket.SHUT_RDWR)
                                except OSError:
                                    pass
                                self.connection.close()
                                return
                            if slow:
                                time.sleep(0.02)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="vodforge-quality-http-origin",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._server = None
        self._thread = None

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(self, *_args: object) -> None:
        self.stop()
