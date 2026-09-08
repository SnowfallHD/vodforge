"""Network routing for telemetry only. Preview cannot reach production sinks."""

from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .telemetry_policy import PREVIEW_ORIGIN, preview_telemetry_allowed


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: Any, msg: Any, headers: Any, newurl: Any
    ) -> None:
        raise OSError("QA telemetry redirects are forbidden")


def telemetry_urlopen(request: urllib.request.Request, **kwargs: Any) -> Any:
    # Cloudflare browser-integrity checks reject urllib's generic agent (1010).
    # Identify our client honestly, without adding device or personal identifiers.
    if not request.has_header("User-agent"):
        request.add_header("User-Agent", "VODForge")
    if not preview_telemetry_allowed():
        return urllib.request.urlopen(request, **kwargs)  # nosec B310 - fixed telemetry endpoints
    url = urllib.parse.urlsplit(request.full_url)
    if (
        url.scheme != "https"
        or url.netloc != "getvodforge.com"
        or not url.path.startswith("/api/")
    ):
        raise OSError("QA telemetry destination forbidden")
    headers = dict(request.header_items())
    headers["X-VODForge-QA-Key"] = os.environ["VODFORGE_QA_ACCESS_KEY"]
    country = os.environ.get("VODFORGE_QA_COUNTRY", "")
    if country in {"US", "DE", "GB", "XX"}:
        headers["X-VODForge-QA-Country"] = country
    routed = urllib.request.Request(
        PREVIEW_ORIGIN + url.path,
        data=request.data,
        headers=headers,
        method=request.get_method(),
    )
    return urllib.request.build_opener(_NoRedirect()).open(routed, **kwargs)
