"""TLS trust for every HTTPS request the app makes itself.

A packaged macOS app's OpenSSL looks for certificates in the build machine's
Python folder (/Library/Frameworks/Python.framework/.../etc/openssl), which
doesn't exist on users' Macs, so a request with Python's default context fails
verification there. Always load the bundled certifi roots, plus whatever the
platform provides (Windows certificate store, custom OpenSSL configuration).
"""

from __future__ import annotations

import ssl
import sys
import urllib.request
from functools import lru_cache
from typing import Any

import certifi


def new_trusted_ssl_context() -> ssl.SSLContext:
    """Certificate and hostname verification stay on; only the roots are added."""
    context = ssl.create_default_context(cafile=certifi.where())
    context.load_default_certs()
    return context


@lru_cache(maxsize=1)
def trusted_ssl_context() -> ssl.SSLContext:
    """Shared context; SSLContext is safe to use from several threads."""
    return new_trusted_ssl_context()


def https_handler() -> urllib.request.HTTPSHandler:
    return urllib.request.HTTPSHandler(context=trusted_ssl_context())


def trusted_urlopen(request: urllib.request.Request | str, **kwargs: Any) -> Any:
    return urllib.request.urlopen(  # nosec B310 - callers pass fixed HTTPS endpoints
        request, context=trusted_ssl_context(), **kwargs
    )


def extend_ytdlp_trust(platform: str = sys.platform) -> bool:
    """On Windows, let yt-dlp also trust the Windows certificate store.

    yt-dlp verifies with certifi alone when it is installed, so users whose
    antivirus or company proxy inspects HTTPS (adding its own root to Windows)
    can't download (production: tls_certificate, verify code 18). Keep certifi
    and add the Windows stores on top, using yt-dlp's own store loader. macOS
    is unchanged: a packaged app has no usable system store there. Applies to
    yt-dlp's standard handlers; its curl_cffi impersonation handler keeps its
    own CA setup. Returns whether the wrapper is in place.
    """
    if platform != "win32" or not hasattr(ssl, "enum_certificates"):
        return False
    try:
        from yt_dlp.networking import _helper
    except ImportError:
        return False
    original = getattr(_helper, "ssl_load_certs", None)
    windows_store = getattr(_helper, "ssl_load_windows_store_certs", None)
    if original is None or windows_store is None:
        return False
    if getattr(original, "vodforge_windows_store", False):
        return True

    def ssl_load_certs(context: ssl.SSLContext, use_certifi: bool = True) -> None:
        original(context, use_certifi)
        if use_certifi:  # Otherwise yt-dlp already loaded the system store.
            for store in ("CA", "ROOT"):
                windows_store(context, store)

    ssl_load_certs.vodforge_windows_store = True  # type: ignore[attr-defined]
    ssl_load_certs.vodforge_original = original  # type: ignore[attr-defined]
    _helper.ssl_load_certs = ssl_load_certs
    return True
