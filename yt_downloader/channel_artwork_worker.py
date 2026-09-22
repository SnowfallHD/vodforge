"""Isolated, deadline-owned public channel profile acquisition; never downloads media."""

from __future__ import annotations

import base64
import io
import json
import sys
from typing import Any

from PIL import Image
from yt_dlp import YoutubeDL

from .thumbnail_network import (
    ThumbnailUrlPolicy,
    download_bounded_url_bytes,
    validated_channel_url,
)


class QuietLogger:
    def debug(self, *_args: Any) -> None:
        pass

    info = warning = error = debug


def profile_thumbnails(info: dict[str, Any]) -> dict[str, str]:
    """Role markers outrank dimensions; a banner can never become an avatar."""
    thumbnails = [
        item for item in (info.get("thumbnails") or [])[:64] if isinstance(item, dict)
    ]
    selected = {}
    for role in ("avatar", "banner"):
        exact = next(
            (item for item in thumbnails if item.get("id") == role + "_uncropped"), None
        )
        if exact and isinstance(exact.get("url"), str):
            selected[role] = exact["url"]
    # The provider marks banner crops with a negative preference. Prefer its
    # full-width 2560px variant to an unbounded original that may exceed byte limits.
    banners = []
    for item in thumbnails:
        try:
            width, height = int(item.get("width") or 0), int(item.get("height") or 0)
            preference = float(item.get("preference") or 0)
        except (TypeError, ValueError, OverflowError):
            continue
        if (
            preference < 0
            and 1000 <= width <= 4096
            and 0 < height <= 2048
            and width >= height * 2
            and isinstance(item.get("url"), str)
        ):
            banners.append((width * height, item["url"]))
    if banners:
        selected["banner"] = max(banners)[1]
    return selected


def acquire_profile(url: str, expected_id: str = "") -> dict[str, Any]:
    url = validated_channel_url(url)
    options = {
        "playlist_items": "0",
        "skip_download": True,
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "cachedir": False,
        "socket_timeout": 3,
        "extractor_retries": 0,
        "retries": 0,
        "logger": QuietLogger(),
    }
    with YoutubeDL(options) as extractor:
        info = extractor.extract_info(url, download=False)
    if not isinstance(info, dict) or (info.get("entries") or []):
        raise ValueError("Unexpected channel metadata")
    channel_id = str(info.get("channel_id") or "")
    if expected_id and channel_id != expected_id:
        raise ValueError("Channel identity changed")
    policy = ThumbnailUrlPolicy.for_youtube_channel(url)
    images = {}
    for role, source in profile_thumbnails(info).items():
        try:
            payload = download_bounded_url_bytes(
                source, policy=policy, timeout_seconds=3, max_bytes=3 * 1024 * 1024
            )
            with Image.open(io.BytesIO(payload)) as original:
                if original.width * original.height > 40_000_000:
                    raise ValueError("Profile image exceeds decode bound")
                image = original.convert("RGB")
            maximum = (1200, 1200) if role == "avatar" else (2560, 1440)
            image.thumbnail(maximum, Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=90)
            data = output.getvalue()
            if len(data) <= 3 * 1024 * 1024:
                images[role] = base64.b64encode(data).decode("ascii")
        except (OSError, ValueError, RuntimeError):
            continue
    return {
        "schema_version": 1,
        "channel_id": channel_id,
        "name": str(info.get("channel") or info.get("title") or "")[:160],
        "description": str(info.get("description") or "")[:2048],
        "images": images,
    }


def main() -> int:
    try:
        data = sys.stdin.buffer.read(4097)
        if len(data) > 4096:
            raise ValueError("Oversized request")
        request = json.loads(data)
        if not isinstance(request, dict):
            raise TypeError("Invalid request")
        result = acquire_profile(
            str(request.get("url") or ""), str(request.get("channel_id") or "")
        )
        sys.stdout.write(json.dumps(result, ensure_ascii=True))
        return 0
    except Exception:  # noqa: BLE001 - isolated provider boundary; no private diagnostics
        sys.stdout.write('{"schema_version":1,"unavailable":true}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
