from __future__ import annotations

from io import BytesIO
from typing import Self
from urllib.request import Request

import pytest

from yt_downloader import thumbnail_network
from yt_downloader.thumbnail_network import (
    ThumbnailUrlPolicy,
    download_bounded_url_bytes,
)


class _Response:
    def __init__(
        self,
        payload: bytes = b"thumbnail",
        *,
        final_url: str = "https://i.ytimg.com/vi/abc123/hqdefault.jpg",
        headers: dict[str, str] | None = None,
    ) -> None:
        self._buffer = BytesIO(payload)
        self._final_url = final_url
        self.headers = headers or {}

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def geturl(self) -> str:
        return self._final_url

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)


class _Opener:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.calls: list[tuple[Request, float]] = []

    def open(self, request: Request, *, timeout: float) -> _Response:
        self.calls.append((request, timeout))
        return self.response


def _install_opener(monkeypatch: pytest.MonkeyPatch, response: _Response) -> _Opener:
    opener = _Opener(response)
    monkeypatch.setattr(
        thumbnail_network.urllib.request, "build_opener", lambda *_handlers: opener
    )
    return opener


@pytest.mark.parametrize(
    "url",
    [
        "https://i.ytimg.com/vi/abc123/hqdefault.jpg",
        "https://img.youtube.com/vi/abc123/maxresdefault.jpg?quality=high",
    ],
)
def test_reviewed_youtube_thumbnail_authorities_are_accepted(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    opener = _install_opener(monkeypatch, _Response(final_url=url))

    assert download_bounded_url_bytes(url, timeout_seconds=7) == b"thumbnail"

    assert opener.calls[0][0].full_url == url
    assert opener.calls[0][1] == 7


@pytest.mark.parametrize(
    "url",
    [
        "file:///private/data",
        "https://user:pass@i.ytimg.com/vi/abc/default.jpg",
        "https://i.ytimg.com:444/vi/abc/default.jpg",
        "http://i.ytimg.com/vi/abc/default.jpg",
        "https://i.ytimg.com.evil.example/vi/abc/default.jpg",
        "https://evil-i.ytimg.com/vi/abc/default.jpg",
        "https://i.ytimg.com/vi/abc/default.jpg#secret",
        "https://i.ytimg.com:invalid/vi/abc/default.jpg",
        "https://i.ytimg.com:0/vi/abc/default.jpg",
        " https://i.ytimg.com/vi/abc/default.jpg",
        "http://127.0.0.1:8080/private.jpg",
        "http://169.254.169.254/latest/meta-data",
    ],
)
def test_untrusted_or_malformed_thumbnail_authorities_are_rejected_before_network(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    monkeypatch.setattr(
        thumbnail_network.urllib.request,
        "build_opener",
        lambda *_handlers: pytest.fail("network opener must not be constructed"),
    )

    with pytest.raises(RuntimeError):
        download_bounded_url_bytes(url)


def test_explicit_source_allows_only_its_exact_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thumbnail_url = "http://127.0.0.1:48123/media/thumbnail.jpg"
    opener = _install_opener(monkeypatch, _Response(final_url=thumbnail_url))

    assert (
        download_bounded_url_bytes(
            thumbnail_url,
            source_url="http://127.0.0.1:48123/media/video.mp4?fixture=1",
        )
        == b"thumbnail"
    )
    assert opener.calls

    with pytest.raises(RuntimeError, match="not trusted"):
        download_bounded_url_bytes(
            "http://127.0.0.1:48124/media/thumbnail.jpg",
            source_url="http://127.0.0.1:48123/media/video.mp4",
        )


def test_https_default_ports_compare_as_the_same_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://fixture.invalid:443/thumbnail.jpg"
    _install_opener(monkeypatch, _Response(final_url=url))

    assert (
        download_bounded_url_bytes(url, source_url="https://fixture.invalid/video.mp4")
        == b"thumbnail"
    )


def test_http_hostname_source_cannot_grant_rebindable_thumbnail_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        thumbnail_network.urllib.request,
        "build_opener",
        lambda *_handlers: pytest.fail("network opener must not be constructed"),
    )

    with pytest.raises(RuntimeError, match="not trusted"):
        download_bounded_url_bytes(
            "http://fixture.invalid/thumbnail.jpg",
            source_url="http://fixture.invalid/video.mp4",
        )


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_policy_validates_every_target(status: int) -> None:
    policy = ThumbnailUrlPolicy.for_source("http://127.0.0.1:48123/video.mp4")
    handler = thumbnail_network._PolicyRedirectHandler(policy)
    request = Request("http://127.0.0.1:48123/thumbnail.jpg")

    redirected = handler.redirect_request(
        request,
        None,
        status,
        "Found",
        {},
        "http://127.0.0.1:48123/next-thumbnail.jpg",
    )
    assert redirected is not None
    assert redirected.full_url == "http://127.0.0.1:48123/next-thumbnail.jpg"

    with pytest.raises(RuntimeError, match="not trusted"):
        handler.redirect_request(
            request,
            None,
            status,
            "Found",
            {},
            "http://127.0.0.1:48124/private-service",
        )


def test_untrusted_final_response_url_is_rejected_before_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnreadableResponse(_Response):
        def read(self, size: int = -1) -> bytes:
            raise AssertionError("an untrusted response must not be read")

    _install_opener(
        monkeypatch,
        UnreadableResponse(final_url="http://169.254.169.254/latest/meta-data"),
    )

    with pytest.raises(RuntimeError, match="not trusted"):
        download_bounded_url_bytes("https://i.ytimg.com/vi/abc123/default.jpg")


def test_declared_and_streamed_byte_limits_are_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_opener(
        monkeypatch,
        _Response(
            b"must not be read",
            headers={"Content-Length": "1001"},
        ),
    )
    with pytest.raises(RuntimeError, match="safety limit"):
        download_bounded_url_bytes("https://i.ytimg.com/oversized.jpg", max_bytes=1000)

    _install_opener(monkeypatch, _Response(b"x" * 1001))
    with pytest.raises(RuntimeError, match="safety limit"):
        download_bounded_url_bytes("https://i.ytimg.com/chunked.jpg", max_bytes=1000)


@pytest.mark.parametrize(
    ("timeout_seconds", "max_bytes"),
    [(0, 1), (-1, 1), (1, 0), (1, -1)],
)
def test_nonpositive_resource_bounds_are_rejected(
    timeout_seconds: float, max_bytes: int
) -> None:
    with pytest.raises(ValueError):
        download_bounded_url_bytes(
            "https://i.ytimg.com/vi/abc123/default.jpg",
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
        )
