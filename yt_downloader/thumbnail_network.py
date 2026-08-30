from __future__ import annotations

import ipaddress
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

THUMBNAIL_DOWNLOAD_MAX_BYTES = 10 * 1024 * 1024
THUMBNAIL_DOWNLOAD_CHUNK_BYTES = 64 * 1024

# These are the video-thumbnail authorities VODForge reconstructs and the
# yt-dlp metadata used by the application currently exposes. Keep this exact:
# suffix matching would allow attacker-controlled deceptive hostnames.
YOUTUBE_THUMBNAIL_HOSTS = frozenset({"i.ytimg.com", "img.youtube.com"})


@dataclass(frozen=True)
class _Origin:
    scheme: str
    host: str
    port: int


def _normalized_origin(url: str, *, label: str) -> _Origin:
    raw_url = str(url)
    if (
        not raw_url
        or raw_url != raw_url.strip()
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in raw_url)
    ):
        raise RuntimeError(f"{label} is malformed")
    try:
        parsed = urllib.parse.urlsplit(raw_url)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            raise RuntimeError(f"{label} must use HTTP or HTTPS")
        if parsed.username is not None or parsed.password is not None:
            raise RuntimeError(f"{label} must not contain user information")
        if not parsed.hostname:
            raise RuntimeError(f"{label} must contain a hostname")
        host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        port = parsed.port
        if not host or port == 0:
            raise RuntimeError(f"{label} has an invalid hostname or port")
    except (UnicodeError, ValueError) as exc:
        raise RuntimeError(f"{label} has an invalid hostname or port") from exc
    return _Origin(
        scheme=scheme,
        host=host,
        port=port if port is not None else (443 if scheme == "https" else 80),
    )


@dataclass(frozen=True)
class ThumbnailUrlPolicy:
    """Authority policy applied to an initial thumbnail URL and every redirect."""

    source_origin: _Origin | None = None

    @classmethod
    def for_source(cls, source_url: str | None = None) -> ThumbnailUrlPolicy:
        origin = None
        if source_url:
            candidate = _normalized_origin(source_url, label="Thumbnail source URL")
            # An HTTPS origin remains bound by certificate validation. Plain HTTP
            # hostnames can DNS-rebind between the source and thumbnail requests,
            # so only an exact IP literal is acceptable for HTTP. This preserves
            # explicitly requested local fixtures without granting provider
            # metadata new network authority.
            if candidate.scheme == "https":
                origin = candidate
            elif candidate.scheme == "http":
                try:
                    ipaddress.ip_address(candidate.host)
                except ValueError:
                    pass
                else:
                    origin = candidate
        return cls(source_origin=origin)

    def validate(self, url: str) -> str:
        raw_url = str(url)
        parsed = urllib.parse.urlsplit(raw_url)
        if parsed.fragment:
            raise RuntimeError("Thumbnail URLs must not contain fragments")
        origin = _normalized_origin(raw_url, label="Thumbnail URL")
        if origin.host in YOUTUBE_THUMBNAIL_HOSTS:
            if origin.scheme != "https" or origin.port != 443:
                raise RuntimeError(
                    "YouTube thumbnail URLs must use the standard HTTPS authority"
                )
            return raw_url
        if self.source_origin is not None and origin == self.source_origin:
            return raw_url
        raise RuntimeError("Thumbnail URL authority is not trusted for this source")


class _PolicyRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, policy: ThumbnailUrlPolicy) -> None:
        super().__init__()
        self._policy = policy

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        self._policy.validate(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_bounded_url_bytes(
    url: str,
    *,
    source_url: str | None = None,
    timeout_seconds: float = 30,
    max_bytes: int = THUMBNAIL_DOWNLOAD_MAX_BYTES,
) -> bytes:
    """Download a thumbnail with strict authority, redirect, time, and memory bounds."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")

    policy = ThumbnailUrlPolicy.for_source(source_url)
    requested_url = policy.validate(url)
    opener = urllib.request.build_opener(_PolicyRedirectHandler(policy))
    request = urllib.request.Request(
        requested_url, headers={"User-Agent": "VODForge thumbnail fetcher"}
    )
    # The initial authority, each redirect, and the reported final URL are all validated.
    with opener.open(request, timeout=timeout_seconds) as response:  # nosec B310
        geturl = getattr(response, "geturl", None)
        final_url = geturl() if callable(geturl) else requested_url
        policy.validate(str(final_url))

        headers = getattr(response, "headers", None)
        content_length = headers.get("Content-Length") if headers is not None else None
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    raise RuntimeError(
                        f"Thumbnail response exceeds the {max_bytes}-byte safety limit"
                    )
            except ValueError:
                pass

        payload = bytearray()
        while True:
            chunk = response.read(
                min(THUMBNAIL_DOWNLOAD_CHUNK_BYTES, max_bytes + 1 - len(payload))
            )
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > max_bytes:
                raise RuntimeError(
                    f"Thumbnail response exceeds the {max_bytes}-byte safety limit"
                )
        return bytes(payload)
