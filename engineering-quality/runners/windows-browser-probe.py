"""Actual Windows default-browser handoff, using a loopback-only receipt page.

This checks OS dispatch, not attribution ingestion or the production claim page.
Never reads browser storage or changes the default browser.
"""

import ctypes
import json
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main():
    destination = Path(sys.argv[1])
    nonce = secrets.token_hex(16)
    title = "VODForge QA " + nonce
    begun = time.monotonic()
    arrived = threading.Event()
    result = {"passed": False, "evidence": "os_default_browser_loopback"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if self.path != "/" + nonce:
                self.send_error(404)
                return
            body = (
                f"<!doctype html><title>{title}</title>"
                "<h1>VODForge browser test finished</h1>"
                "<p>This isolated test sends no production analytics. You can close this tab.</p>"
                f"<script>fetch('/{nonce}',{{method:'POST',body:JSON.stringify({{visibility:document.visibilityState}})}})</script>"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/" + nonce:
                self.send_error(404)
                return
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size < 256:
                self.send_error(400)
                return
            value = json.loads(self.rfile.read(size))
            result.update(
                passed=True,
                page_seconds=round(time.monotonic() - begun, 3),
                visibility=value.get("visibility"),
            )
            self.send_response(204)
            self.end_headers()
            arrived.set()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        result["dispatch_return"] = webbrowser.open(
            f"http://127.0.0.1:{server.server_port}/{nonce}", new=2, autoraise=False
        )
        arrived.wait(20)
        # Close only our foreground tab; never close an entire browser/process.
        # If focus moved elsewhere, leave the harmless test page alone.
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        window = user32.GetForegroundWindow()
        text = ctypes.create_unicode_buffer(1024)
        user32.GetWindowTextW(ctypes.c_void_p(window), text, len(text))
        result["foreground_is_test_page"] = title in text.value
        if result["foreground_is_test_page"]:
            user32.keybd_event(0x11, 0, 0, 0)
            user32.keybd_event(0x57, 0, 0, 0)
            user32.keybd_event(0x57, 0, 2, 0)
            user32.keybd_event(0x11, 0, 2, 0)
            result["test_tab_close_requested"] = True
    finally:
        server.shutdown()
        server.server_close()
        destination.write_text(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
