from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from yt_downloader.updates import (
    ReleaseAsset,
    ReleaseInfo,
    download_verified_update,
    is_newer_release,
    parse_release_payload,
    parse_sha256sums,
    release_asset_for_platform,
    semantic_version_key,
)
from yt_downloader.version import DEFAULT_VERSION, read_app_version


def test_semantic_versions_treat_stable_release_as_newer_than_dev_build():
    assert semantic_version_key("v1.2.3") > semantic_version_key("1.2.3-dev")
    assert is_newer_release("0.1.0-dev", "v0.1.0")
    assert not is_newer_release("0.2.0", "v0.1.9")


def test_release_payload_accepts_only_public_stable_github_release():
    release = parse_release_payload(
        {
            "tag_name": "v1.2.3",
            "name": "VODForge 1.2.3",
            "html_url": "https://github.com/SnowfallHD/vodforge/releases/tag/v1.2.3",
            "body": "Release notes",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": "VODForge-Windows-Setup-v1.2.3.exe",
                    "browser_download_url": "https://github.com/SnowfallHD/vodforge/releases/download/v1.2.3/VODForge-Windows-Setup-v1.2.3.exe",
                    "size": 123,
                }
            ],
        }
    )

    assert release.version == "1.2.3"
    assert release.tag_name == "v1.2.3"
    assert release.assets[0].size == 123


@pytest.mark.parametrize(
    "payload",
    [
        {"tag_name": "v1.2.3", "html_url": "https://evil.example/release", "draft": False, "prerelease": False},
        {"tag_name": "latest", "html_url": "https://github.com/SnowfallHD/vodforge/releases/latest", "draft": False, "prerelease": False},
        {"tag_name": "v1.2.3-beta.1", "html_url": "https://github.com/SnowfallHD/vodforge/releases/tag/v1.2.3-beta.1", "draft": False, "prerelease": False},
        {"tag_name": "v1.2.3", "html_url": "https://github.com/SnowfallHD/vodforge/releases/tag/v1.2.3", "draft": True, "prerelease": False},
    ],
)
def test_release_payload_rejects_untrusted_or_nonstable_data(payload: dict[str, object]):
    with pytest.raises(ValueError):
        parse_release_payload(payload)


def test_packaged_version_file_is_validated(tmp_path: Path):
    version_file = tmp_path / "VODFORGE_VERSION"
    version_file.write_text("1.4.2\n", encoding="utf-8")
    assert read_app_version(version_file) == "1.4.2"

    version_file.write_text("not-a-version", encoding="utf-8")
    assert read_app_version(version_file) == DEFAULT_VERSION


def test_platform_asset_selection_is_exact():
    release = ReleaseInfo(
        version="1.2.3",
        tag_name="v1.2.3",
        name="VODForge 1.2.3",
        html_url="https://github.com/SnowfallHD/vodforge/releases/tag/v1.2.3",
        notes="",
        assets=(
            ReleaseAsset("VODForge-Windows-Setup-v1.2.3.exe", "https://github.com/example/windows", 10),
            ReleaseAsset("VODForge-macOS-arm64-v1.2.3.zip", "https://github.com/example/mac-arm", 10),
            ReleaseAsset("VODForge-macOS-x64-v1.2.3.zip", "https://github.com/example/mac-x64", 10),
        ),
    )

    assert release_asset_for_platform(release, platform_name="win32", machine="AMD64").name.endswith(".exe")
    assert release_asset_for_platform(release, platform_name="darwin", machine="arm64").name == "VODForge-macOS-arm64-v1.2.3.zip"
    assert release_asset_for_platform(release, platform_name="darwin", machine="x86_64").name == "VODForge-macOS-x64-v1.2.3.zip"
    assert release_asset_for_platform(release, platform_name="linux", machine="x86_64") is None


def test_verified_update_requires_matching_checksum(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    update_bytes = b"verified installer bytes"
    digest = hashlib.sha256(update_bytes).hexdigest()
    asset_name = "VODForge-Windows-Setup-v1.2.3.exe"
    release = ReleaseInfo(
        version="1.2.3",
        tag_name="v1.2.3",
        name="VODForge 1.2.3",
        html_url="https://github.com/SnowfallHD/vodforge/releases/tag/v1.2.3",
        notes="",
        assets=(
            ReleaseAsset(asset_name, "https://github.com/example/update", len(update_bytes)),
            ReleaseAsset("SHA256SUMS.txt", "https://github.com/example/checksums", 80),
        ),
    )

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    def fake_urlopen(request, timeout=0):
        assert timeout == 60
        if request.full_url.endswith("checksums"):
            return FakeResponse(f"{digest}  {asset_name}\n".encode())
        return FakeResponse(update_bytes)

    monkeypatch.setattr("yt_downloader.updates.urllib.request.urlopen", fake_urlopen)
    output = download_verified_update(release, tmp_path, platform_name="win32", machine="AMD64")

    assert output.read_bytes() == update_bytes
    assert parse_sha256sums(f"{digest}  {asset_name}\n") == {asset_name: digest}


def test_verified_update_deletes_tampered_partial_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    asset_name = "VODForge-Windows-Setup-v1.2.3.exe"
    release = ReleaseInfo(
        version="1.2.3",
        tag_name="v1.2.3",
        name="VODForge 1.2.3",
        html_url="https://github.com/SnowfallHD/vodforge/releases/tag/v1.2.3",
        notes="",
        assets=(
            ReleaseAsset(asset_name, "https://github.com/example/update", 8),
            ReleaseAsset("SHA256SUMS.txt", "https://github.com/example/checksums", 80),
        ),
    )

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    responses = iter([FakeResponse(f"{'0' * 64}  {asset_name}\n".encode()), FakeResponse(b"tampered")])
    monkeypatch.setattr("yt_downloader.updates.urllib.request.urlopen", lambda *_args, **_kwargs: next(responses))

    with pytest.raises(RuntimeError, match="SHA-256 verification"):
        download_verified_update(release, tmp_path, platform_name="win32", machine="AMD64")

    assert not (tmp_path / asset_name).exists()
    assert not (tmp_path / f"{asset_name}.part").exists()
