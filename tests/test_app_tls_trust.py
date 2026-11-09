"""Every HTTPS request the app makes itself verifies with the bundled roots.

A packaged Mac app's OpenSSL points at the build machine's Python folder, which
users don't have. 0.2.6's analytics requests used Python's default context, so
on users' Macs the region check, registration, events and PostHog all failed
verification: the region fell back to "unknown" (consent prompt everywhere) and
nothing was delivered. These tests run with the platform paths made unusable,
as on such a Mac.
"""

from __future__ import annotations

import re
import ssl
import urllib.request
from pathlib import Path

import pytest

from yt_downloader import posthog_analytics, support_transport, telemetry_transport, tls

ROOT = Path(__file__).resolve().parents[1] / "yt_downloader"


@pytest.fixture
def no_platform_roots(monkeypatch, tmp_path):
    missing = tmp_path / "missing"
    monkeypatch.setenv("SSL_CERT_FILE", str(missing / "cert.pem"))
    monkeypatch.setenv("SSL_CERT_DIR", str(missing))
    monkeypatch.setattr(ssl.SSLContext, "load_default_certs", lambda *_a, **_k: None)
    tls.trusted_ssl_context.cache_clear()
    yield
    tls.trusted_ssl_context.cache_clear()


def bundled(context: ssl.SSLContext) -> bool:
    return (
        context.verify_mode == ssl.CERT_REQUIRED
        and context.check_hostname
        and context.cert_store_stats()["x509_ca"] >= 50
    )


def test_default_context_has_no_roots_on_such_a_mac(no_platform_roots):
    # The failure this file guards against: the default context is empty.
    context = ssl.create_default_context()
    context.load_default_certs()
    assert context.cert_store_stats()["x509_ca"] == 0
    assert bundled(tls.trusted_ssl_context())


def capture_contexts(monkeypatch) -> list[ssl.SSLContext]:
    seen: list[ssl.SSLContext] = []

    def urlopen(request, *args, context=None, **kwargs):
        seen.append(context)
        return "response"

    class Opener:
        def __init__(self, handlers):
            self.handlers = handlers

        def open(self, request, **kwargs):
            for handler in self.handlers:
                if isinstance(handler, urllib.request.HTTPSHandler):
                    seen.append(handler._context)
            return "response"

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *handlers: Opener(handlers)
    )
    return seen


@pytest.mark.parametrize("follow_redirects", [True, False])
def test_telemetry_transport_uses_bundled_roots(
    no_platform_roots, monkeypatch, follow_redirects
):
    seen = capture_contexts(monkeypatch)
    request = urllib.request.Request("https://getvodforge.com/api/analytics/policy")
    telemetry_transport.telemetry_urlopen(
        request, follow_redirects=follow_redirects, timeout=1
    )
    assert len(seen) == 1 and bundled(seen[0])


def test_posthog_sink_uses_bundled_roots(no_platform_roots, monkeypatch):
    seen = capture_contexts(monkeypatch)
    sink = posthog_analytics.PosthogEventSink()
    sink._opener(urllib.request.Request("https://us.i.posthog.com/i/v0/e/"), timeout=1)
    assert len(seen) == 1 and bundled(seen[0])


def test_support_transport_uses_bundled_roots(no_platform_roots, monkeypatch):
    seen = capture_contexts(monkeypatch)
    with pytest.raises(Exception):  # noqa: B017 - the fake response is not JSON
        support_transport.SupportTransport.__new__(
            support_transport.SupportTransport
        )._post("feedback", {}, {"credential_id": "c", "secret": "s"})
    assert len(seen) == 1 and bundled(seen[0])


def test_no_network_call_skips_the_shared_trust():
    """New HTTPS code must pass the shared context or handler."""
    offenders = []
    for path in ROOT.rglob("*.py"):
        if path.name == "tls.py":
            continue
        lines = path.read_text("utf-8").splitlines()
        for number, line in enumerate(lines, 1):
            call = " ".join(lines[number - 1 : number + 3])  # calls can wrap
            if (
                re.search(r"urllib\.request\.urlopen\(", line)
                and "context=" not in call
            ):
                offenders.append(f"{path.name}:{number}")
            if (
                re.search(r"build_opener\(", line)
                and not re.search(r"https_handler\(\)|HTTPSHandler\(", call)
                and "loopback" not in call
            ):
                offenders.append(f"{path.name}:{number}")
    assert offenders == []
