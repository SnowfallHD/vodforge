from __future__ import annotations

import json
import hashlib
import os
import platform
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


GITHUB_REPOSITORY = "SnowfallHD/vodforge"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPOSITORY}/releases/latest"
MAX_RELEASE_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_UPDATE_ASSET_BYTES = 4 * 1024 * 1024 * 1024
SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")
SHA256_RE = re.compile(r"^([0-9a-fA-F]{64})\s+[ *](.+)$")


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    download_url: str
    size: int


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag_name: str
    name: str
    html_url: str
    notes: str
    assets: tuple[ReleaseAsset, ...]


def semantic_version_key(version: str) -> tuple[int, int, int, int, str]:
    match = SEMVER_RE.fullmatch(str(version).strip())
    if not match:
        raise ValueError(f"Unsupported release version: {version!r}")
    major, minor, patch = (int(match.group(index)) for index in range(1, 4))
    prerelease = match.group(4) or ""
    return major, minor, patch, 1 if not prerelease else 0, prerelease


def is_newer_release(current_version: str, release_version: str) -> bool:
    return semantic_version_key(release_version) > semantic_version_key(current_version)


def _trusted_github_page(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        raise ValueError("GitHub returned an invalid release page URL.")
    return url


def _trusted_github_download(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        raise ValueError("GitHub returned an invalid release download URL.")
    return url


def parse_release_payload(payload: dict[str, Any]) -> ReleaseInfo:
    if payload.get("draft") or payload.get("prerelease"):
        raise ValueError("GitHub's latest release is not a public stable release.")
    tag_name = str(payload.get("tag_name") or "").strip()
    version_match = SEMVER_RE.fullmatch(tag_name)
    if not version_match:
        raise ValueError("GitHub's latest release does not use a semantic version tag.")
    if version_match.group(4):
        raise ValueError("GitHub's latest release is not a stable semantic version.")
    version = ".".join(version_match.group(index) for index in range(1, 4))
    assets: list[ReleaseAsset] = []
    for raw_asset in payload.get("assets") or []:
        if not isinstance(raw_asset, dict):
            continue
        name = str(raw_asset.get("name") or "").strip()
        download_url = str(raw_asset.get("browser_download_url") or "").strip()
        try:
            size = int(raw_asset.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if not name or not download_url:
            continue
        assets.append(ReleaseAsset(name=name, download_url=_trusted_github_download(download_url), size=size))
    return ReleaseInfo(
        version=version,
        tag_name=tag_name,
        name=str(payload.get("name") or tag_name).strip(),
        html_url=_trusted_github_page(str(payload.get("html_url") or "").strip()),
        notes=str(payload.get("body") or "").strip(),
        assets=tuple(assets),
    )


def fetch_latest_release(*, timeout: float = 15) -> ReleaseInfo:
    request = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"VODForge update checker ({GITHUB_REPOSITORY})",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RELEASE_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError("No packaged VODForge release is available yet.") from exc
        raise RuntimeError(f"GitHub could not check for updates (HTTP {exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("VODForge could not reach GitHub to check for updates.") from exc
    if len(raw) > MAX_RELEASE_RESPONSE_BYTES:
        raise RuntimeError("GitHub returned an unexpectedly large release response.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("GitHub returned an unreadable release response.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub returned an invalid release response.")
    return parse_release_payload(payload)


def release_asset_for_platform(
    release: ReleaseInfo,
    *,
    platform_name: str | None = None,
    machine: str | None = None,
) -> ReleaseAsset | None:
    platform_name = sys.platform if platform_name is None else platform_name
    machine = platform.machine().lower() if machine is None else machine.lower()
    if platform_name.startswith("win"):
        expected = f"VODForge-Windows-Setup-v{release.version}.exe"
    elif platform_name == "darwin":
        architecture = "arm64" if machine in {"arm64", "aarch64"} else "x64"
        expected = f"VODForge-macOS-{architecture}-v{release.version}.zip"
    else:
        return None
    return next((asset for asset in release.assets if asset.name == expected), None)


def parse_sha256sums(text: str) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for raw_line in text.splitlines():
        match = SHA256_RE.fullmatch(raw_line.strip())
        if match:
            checksums[match.group(2)] = match.group(1).lower()
    return checksums


def _fetch_small_text(url: str, *, timeout: float) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": f"VODForge updater ({GITHUB_REPOSITORY})"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RELEASE_RESPONSE_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise RuntimeError("VODForge could not download the release checksums.") from exc
    if len(raw) > MAX_RELEASE_RESPONSE_BYTES:
        raise RuntimeError("The release checksum file is unexpectedly large.")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("The release checksum file is unreadable.") from exc


def download_verified_update(
    release: ReleaseInfo,
    destination_dir: Path,
    *,
    platform_name: str | None = None,
    machine: str | None = None,
    timeout: float = 60,
) -> Path:
    asset = release_asset_for_platform(release, platform_name=platform_name, machine=machine)
    if asset is None:
        raise RuntimeError("This release does not include an update for this computer.")
    if asset.size <= 0 or asset.size > MAX_UPDATE_ASSET_BYTES:
        raise RuntimeError("The release update has an invalid file size.")
    checksum_asset = next((item for item in release.assets if item.name == "SHA256SUMS.txt"), None)
    if checksum_asset is None:
        raise RuntimeError("This release is missing its SHA-256 checksum manifest.")
    expected_hash = parse_sha256sums(_fetch_small_text(checksum_asset.download_url, timeout=timeout)).get(asset.name)
    if not expected_hash:
        raise RuntimeError("This release is missing the update file's SHA-256 checksum.")

    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / asset.name
    temporary = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256()
    downloaded = 0
    request = urllib.request.Request(asset.download_url, headers={"User-Agent": f"VODForge updater ({GITHUB_REPOSITORY})"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, temporary.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > asset.size or downloaded > MAX_UPDATE_ASSET_BYTES:
                    raise RuntimeError("The release update exceeded its declared file size.")
                digest.update(chunk)
                output.write(chunk)
        if downloaded != asset.size:
            raise RuntimeError("The release update did not match its declared file size.")
        if digest.hexdigest().lower() != expected_hash:
            raise RuntimeError("The release update failed SHA-256 verification and was not opened.")
        temporary.replace(destination)
        if os.name != "nt":
            destination.chmod(0o700)
        return destination
    except (OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise RuntimeError("VODForge could not download the release update.") from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
