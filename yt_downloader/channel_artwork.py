"""Bounded cached channel identity artwork, independent of video thumbnails."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import subprocess  # nosec B404 - fixed first-party worker invocation
import sys
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from PIL import Image

from .platform_services import hidden_window_subprocess_kwargs
from .private_files import write_private_bytes
from .thumbnail_network import validated_channel_url

PROFILE_TTL = 7 * 24 * 60 * 60
PROFILE_LIMIT = 128


def channel_request(record: dict[str, Any]) -> tuple[str, str] | None:
    try:
        channel_url = str(record.get("channel_url") or record.get("uploader_url") or "")
        source = str(
            record.get("webpage_url") or record.get("original_url") or channel_url
        )
        parsed = urlsplit(source)
        if (
            parsed.scheme != "https"
            or parsed.port not in {None, 443}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.hostname
            not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
        ):
            return None
        identity = str(record.get("channel_id") or "")
        if re.fullmatch(r"UC[A-Za-z0-9_-]{22}", identity):
            return validated_channel_url(
                "https://www.youtube.com/channel/" + identity
            ), identity
        return validated_channel_url(channel_url), ""
    except (ValueError, RuntimeError):
        return None


def _profile_key(request: tuple[str, str]) -> str:
    return hashlib.sha256(request[0].encode()).hexdigest()


class ChannelArtworkOwner:
    def __init__(
        self,
        cache_dir: Path,
        *,
        clock: Callable[[], float] = time.time,
        loader: Callable[..., dict[str, Any] | None] | None = None,
    ) -> None:
        self.cache_dir, self._clock = cache_dir, clock
        self._loader = loader or self._load_worker
        self._profiles: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._retry: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.Lock()
        self._closed = threading.Event()

    def close(self) -> None:
        self._closed.set()

    def snapshot(self, record: dict[str, Any]) -> dict[str, str]:
        request = channel_request(record)
        profile = self._profiles.get(_profile_key(request)) if request else None
        return (
            {
                "name": str(profile.get("name") or ""),
                "description": str(profile.get("description") or ""),
            }
            if profile
            else {}
        )

    def resolve(
        self, record: dict[str, Any], role: str, cancelled: threading.Event
    ) -> Path | None:
        request = channel_request(record)
        if role not in {"avatar", "banner"} or not request:
            return None
        key = _profile_key(request)
        while not self._lock.acquire(timeout=0.1):
            if self._closed.is_set() or cancelled.is_set():
                return None
        try:
            if self._closed.is_set() or cancelled.is_set():
                return None
            profile = self._profiles.get(key)
            manifest = self.cache_dir / (key + ".json")
            if profile is None:
                try:
                    if manifest.stat().st_size <= 16 * 1024:
                        candidate = json.loads(manifest.read_text())
                        if (
                            isinstance(candidate, dict)
                            and candidate.get("schema_version") == 1
                            and (
                                not request[1]
                                or candidate.get("channel_id") == request[1]
                            )
                            and isinstance(candidate.get("roles"), list)
                            and set(candidate["roles"]) <= {"avatar", "banner"}
                        ):
                            profile = candidate
                except (OSError, ValueError, TypeError):
                    pass
            now = self._clock()
            fresh = False
            if profile:
                try:
                    fresh = (
                        0
                        <= now - float(profile["saved_at"])
                        < (PROFILE_TTL if len(profile.get("roles", [])) == 2 else 300)
                    )
                except (KeyError, TypeError, ValueError, OverflowError):
                    pass
            if not fresh and self._retry.get(key, 0) <= now:
                self._retry[key] = now + 300
                self._retry.move_to_end(key)
                while len(self._retry) > PROFILE_LIMIT:
                    self._retry.popitem(last=False)
                result = self._loader(request, cancelled)
                if cancelled.is_set() or self._closed.is_set():
                    self._retry.pop(key, None)
                    return None
                if result:
                    profile = self._commit(key, request, result, now) or profile
            if profile:
                self._profiles[key] = profile
                self._profiles.move_to_end(key)
                while len(self._profiles) > PROFILE_LIMIT:
                    self._profiles.popitem(last=False)
                path = self.cache_dir / (key + "-" + role + ".jpg")
                if role in profile.get("roles", []) and path.is_file():
                    return path
            return None
        finally:
            self._lock.release()

    def _commit(
        self, key: str, request: tuple[str, str], result: dict[str, Any], now: float
    ) -> dict[str, Any] | None:
        if result.get("schema_version") != 1 or (
            request[1] and result.get("channel_id") != request[1]
        ):
            return None
        roles = []
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            images = result.get("images")
            for role in ("avatar", "banner"):
                encoded = images.get(role) if isinstance(images, dict) else None
                if not isinstance(encoded, str) or len(encoded) > 4 * 1024 * 1024:
                    continue
                data = base64.b64decode(encoded, validate=True)
                with Image.open(io.BytesIO(data)) as image:
                    if image.width * image.height > 4_000_000:
                        continue
                    image.verify()
                write_private_bytes(self.cache_dir / (key + "-" + role + ".jpg"), data)
                roles.append(role)
            # A missing role is cached too; offline fallback remains usable.
            profile = {
                "schema_version": 1,
                "channel_id": str(result.get("channel_id") or "")[:24],
                "name": str(result.get("name") or "")[:160],
                "description": str(result.get("description") or "")[:2048],
                "saved_at": now,
                "roles": roles,
            }
            write_private_bytes(
                self.cache_dir / (key + ".json"), json.dumps(profile).encode()
            )
            self._prune()
            return profile
        except (OSError, ValueError):
            return None

    def _load_worker(
        self, request: tuple[str, str], cancelled: threading.Event
    ) -> dict[str, Any] | None:
        command = (
            [sys.executable, "--channel-artwork-worker"]
            if getattr(sys, "frozen", False)
            else [sys.executable, "-m", "yt_downloader.channel_artwork_worker"]
        )
        process = None
        try:
            process = subprocess.Popen(  # nosec B603 - first-party worker, no shell
                command,
                cwd=Path(__file__).resolve().parents[1],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                **hidden_window_subprocess_kwargs(),
            )
            deadline = time.monotonic() + 9
            first = True
            while True:
                if (
                    cancelled.is_set()
                    or self._closed.is_set()
                    or time.monotonic() >= deadline
                ):
                    process.kill()
                    process.communicate(timeout=2)
                    return None
                try:
                    payload = (
                        json.dumps(
                            {"url": request[0], "channel_id": request[1]}
                        ).encode()
                        if first
                        else None
                    )
                    first = False
                    output, _ = process.communicate(input=payload, timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode or len(output) > 8 * 1024 * 1024:
                return None
            result = json.loads(output)
            return result if isinstance(result, dict) else None
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate(timeout=2)

    def _prune(self) -> None:
        try:
            manifests = sorted(
                self.cache_dir.glob("*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            for manifest in manifests[PROFILE_LIMIT:]:
                if not re.fullmatch(r"[0-9a-f]{64}", manifest.stem):
                    continue
                for path in (
                    manifest,
                    *(
                        self.cache_dir / (manifest.stem + "-" + role + ".jpg")
                        for role in ("avatar", "banner")
                    ),
                ):
                    path.unlink(missing_ok=True)
        except OSError:
            return
