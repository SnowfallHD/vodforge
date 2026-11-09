"""yt-dlp also trusts the Windows certificate store, on top of certifi.

Production 0.2.5 Windows: a YouTube analysis failed with tls_certificate (verify
code 18) because antivirus or a company proxy inspected HTTPS with a root it had
added to Windows, and yt-dlp verifies with certifi alone. These tests run a real
local HTTPS server whose certificate chains to such a root, with the Windows
store simulated (nothing is installed into a real store).
"""

from __future__ import annotations

import http.server
import ssl
import threading
from pathlib import Path

import pytest

from yt_downloader import tls

yt_dlp = pytest.importorskip("yt_dlp")
from yt_dlp.networking import _helper
from yt_dlp.networking.exceptions import CertificateVerifyError

FIXTURES = Path(__file__).parent / "fixtures" / "intercepting-root"


@pytest.fixture
def intercepted_server():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"intercepted ok"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(FIXTURES / "server.pem", FIXTURES / "server.key")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"https://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()
    server.server_close()


def simulate_windows_store(monkeypatch):
    """A Windows store holding the intercepting root, and yt-dlp's own loader.

    On Windows, importing the channel-artwork worker (tests/test_channel_artwork.py
    does at collection) already wraps yt-dlp's loader for the whole session, so
    start from the original rather than whatever is installed. The wrapper is put
    back after the test.
    """
    root = (FIXTURES / "root.der").read_bytes()

    def enum_certificates(store):
        return [(root, "x509_asn", True)] if store == "ROOT" else []

    monkeypatch.setattr(ssl, "enum_certificates", enum_certificates, raising=False)
    current = _helper.ssl_load_certs
    monkeypatch.setattr(
        _helper, "ssl_load_certs", getattr(current, "vodforge_original", current)
    )


@pytest.fixture
def windows_store_with_intercepting_root(monkeypatch):
    simulate_windows_store(monkeypatch)


def fetch(url: str) -> bytes:
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        return ydl.urlopen(url).read()


def test_without_the_store_yt_dlp_rejects_an_intercepting_root(
    intercepted_server, windows_store_with_intercepting_root
):
    with pytest.raises(CertificateVerifyError):
        fetch(intercepted_server)


def test_rejection_still_holds_when_the_app_wrapped_yt_dlp_earlier(
    intercepted_server, monkeypatch
):
    """Windows CI ran this file after the artwork worker had wrapped yt-dlp, so the
    check above saw the wrapper and passed the connection (Nov 9 tagged Tests)."""
    root = (FIXTURES / "root.der").read_bytes()
    monkeypatch.setattr(
        ssl, "enum_certificates", lambda s: [(root, "x509_asn", True)], raising=False
    )
    monkeypatch.setattr(_helper, "ssl_load_certs", _helper.ssl_load_certs)
    assert tls.extend_ytdlp_trust(platform="win32") is True  # as on Windows
    assert fetch(intercepted_server) == b"intercepted ok"
    simulate_windows_store(monkeypatch)
    with pytest.raises(CertificateVerifyError):
        fetch(intercepted_server)


def test_with_the_store_yt_dlp_accepts_it_and_keeps_certifi(
    intercepted_server, windows_store_with_intercepting_root
):
    assert tls.extend_ytdlp_trust(platform="win32") is True
    assert tls.extend_ytdlp_trust(platform="win32") is True  # idempotent
    assert fetch(intercepted_server) == b"intercepted ok"
    context = _helper.make_ssl_context()
    roots = {cert["subject"] for cert in context.get_ca_certs()}
    assert context.cert_store_stats()["x509_ca"] >= 50  # certifi still loaded
    assert any("intercepting root" in str(subject) for subject in roots)


def test_other_platforms_are_unchanged(monkeypatch):
    monkeypatch.setattr(_helper, "ssl_load_certs", _helper.ssl_load_certs)
    before = _helper.ssl_load_certs
    assert tls.extend_ytdlp_trust(platform="darwin") is False
    assert _helper.ssl_load_certs is before


def test_system_store_mode_is_not_loaded_twice(
    windows_store_with_intercepting_root, monkeypatch
):
    calls = []
    monkeypatch.setattr(
        _helper, "ssl_load_windows_store_certs", lambda _c, store: calls.append(store)
    )
    monkeypatch.setattr(_helper, "ssl_load_certs", lambda _c, _u=True: None)
    tls.extend_ytdlp_trust(platform="win32")
    _helper.ssl_load_certs(ssl.create_default_context(), False)
    assert calls == []
    _helper.ssl_load_certs(ssl.create_default_context(), True)
    assert calls == ["CA", "ROOT"]
