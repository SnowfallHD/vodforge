"""TLS trust for every HTTPS request the app makes itself.

A packaged macOS app's OpenSSL looks for certificates in the build machine's
Python folder (/Library/Frameworks/Python.framework/.../etc/openssl), which
doesn't exist on users' Macs, so a request with Python's default context fails
verification there. Always load the bundled certifi roots, plus whatever the
platform provides (Windows certificate store, custom OpenSSL configuration).
"""

from __future__ import annotations

import ssl
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
